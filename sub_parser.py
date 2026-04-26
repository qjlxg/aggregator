import os
import re
import base64
import json
import requests
import yaml
import hashlib
import geoip2.database
import socket
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote

# 配置
LINK = os.environ.get('LINK', '')
OUTPUT_DIR = 'data'
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"

# 确保目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def download_geoip():
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"警告: 未找到 {GEOIP_DB_PATH}")

def get_country(host, reader):
    try:
        ip = host
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            ip = socket.gethostbyname(host)
        response = reader.country(ip)
        return response.country.names.get('zh-CN', response.country.name) or "Unknown"
    except:
        return "Unknown"

def get_md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:8]

def safe_base64_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except:
        return ""

def extract_nodes(content):
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content, re.IGNORECASE)

def fetch_content(url):
    if not url: return ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        text = resp.text.strip()
        if "://" not in text:
            decoded = safe_base64_decode(text)
            if "://" in decoded: return decoded
        return text
    except:
        return ""

def parse_and_rename():
    download_geoip()
    raw_data = fetch_content(LINK)
    uris = extract_nodes(raw_data)
    
    print(f"正则提取到原始 URI 数量: {len(uris)}")
    
    if not os.path.exists(GEOIP_DB_PATH):
        print("缺少数据库文件")
        return
        
    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    clash_proxies = []
    final_uris = []
    
    for index, uri in enumerate(uris):
        try:
            # 分离协议和后续内容
            scheme, rest = uri.split('://', 1)
            scheme = scheme.lower()
            
            proxy_info = {}
            host = ""
            
            # --- 1. VMESS 解析 ---
            if scheme == 'vmess':
                v2_data = json.loads(safe_base64_decode(rest))
                host = v2_data.get('add')
                proxy_info = {
                    "type": "vmess", "server": host, "port": int(v2_data.get('port', 443)),
                    "uuid": v2_data.get('id'), "alterId": int(v2_data.get('aid', 0)),
                    "cipher": "auto", "tls": True if v2_data.get('tls') == "tls" else False,
                    "network": v2_data.get('net', 'tcp'), "servername": v2_data.get('sni', ''), "udp": True
                }
                if v2_data.get('net') in ['ws', 'grpc']:
                    opt = {"path": v2_data.get('path', '/'), "headers": {"Host": v2_data.get('host', '')}}
                    proxy_info[f"{v2_data['net']}-opts"] = opt

            # --- 2. 其他明文协议解析 (VLESS, Trojan, SS, Hy2) ---
            else:
                # 兼容性处理：去除备注部分再解析
                core_part = rest.split('#')[0]
                # 正则解析格式: uuid@host:port
                match = re.match(r'^(?P<user>.*)@(?P<host>[^:]+):(?P<port>\d+)', core_part)
                if not match: continue
                
                host = match.group('host')
                port = int(match.group('port'))
                user = unquote(match.group('user'))
                
                proxy_info = {"server": host, "port": port, "udp": True}
                
                # 获取查询参数
                query = {}
                if '?' in core_part:
                    query = {k: v[0] for k, v in parse_qs(core_part.split('?')[1]).items()}

                if scheme == 'vless':
                    proxy_info.update({
                        "type": "vless", "uuid": user, 
                        "tls": True if query.get('security') in ['tls', 'reality'] else False,
                        "flow": query.get('flow', ''), "servername": query.get('sni', '')
                    })
                    if query.get('type') == 'ws':
                        proxy_info.update({"network": "ws", "ws-opts": {"path": query.get('path', '/'), "headers": {"Host": query.get('host', '')}}})
                
                elif scheme == 'trojan':
                    proxy_info.update({"type": "trojan", "password": user, "sni": query.get('sni', '')})
                
                elif scheme in ['ss', 'shadowsocks']:
                    proxy_info["type"] = "ss"
                    if ':' in user:
                        proxy_info["cipher"], proxy_info["password"] = user.split(':', 1)
                
                elif scheme in ['hysteria2', 'hy2']:
                    proxy_info.update({"type": "hysteria2", "password": user, "sni": query.get('sni', ''), "alpn": ["h3"]})

            # --- 3. 定位与命名 ---
            if not host or not proxy_info: continue
            
            country = get_country(host, reader)
            md5_tag = get_md5(uri + str(index))
            new_name = f"{country}_{index + 1}_{md5_tag}"
            
            proxy_info["name"] = new_name
            clash_proxies.append(proxy_info)
            final_uris.append(f"{uri.split('#')[0]}#{new_name}")

        except Exception as e:
            # 打印错误方便在 GitHub Actions 日志中排查
            print(f"解析节点 {index} 失败: {e}")
            continue

    reader.close()

    # --- 4. 写入文件 ---
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"成功！提取节点: {len(final_uris)}")

if __name__ == "__main__":
    parse_and_rename()
