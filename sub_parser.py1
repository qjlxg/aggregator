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
        print(f"警告: 根目录未找到 {GEOIP_DB_PATH}")

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
    # 根据要求改为 3 位
    return hashlib.md5(content.encode()).hexdigest()[:3]

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
    # 使用非捕获组确保返回完整 URI
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content, re.IGNORECASE)

def fetch_content(url):
    if not url: return ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        text = resp.text.strip()
        # 自动识别 Base64 列表
        if "://" not in text and "proxies:" not in text:
            decoded = safe_base64_decode(text)
            if "://" in decoded: return decoded
        return text
    except:
        return ""

def parse_and_rename():
    download_geoip()
    # 支持 LINK 中有多个 URL (用空格或逗号分隔)
    urls = re.split(r'[,\s]+', LINK.strip())
    
    if not os.path.exists(GEOIP_DB_PATH):
        print("缺少数据库文件")
        return
        
    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    clash_proxies = []
    final_uris = []
    
    # 遍历所有 URL
    for url in urls:
        if not url: continue
        raw_data = fetch_content(url)
        if not raw_data: continue

        current_nodes = []
        # --- 识别 YAML 格式 ---
        if "proxies:" in raw_data:
            try:
                y_data = yaml.safe_load(raw_data)
                if y_data and 'proxies' in y_data:
                    # 简单转换：此处由于 YAML 转 URI 非常复杂，通常建议只处理 URI 格式
                    # 但为了满足需求，我们将 YAML 节点存入待处理列表
                    for p in y_data['proxies']:
                        # 将简单核心信息存入，后续统一重命名
                        current_nodes.append(('clash_obj', p))
            except: pass
        
        # --- 识别 URI 格式 ---
        uris = extract_nodes(raw_data)
        for u in uris:
            current_nodes.append(('uri', u))

        # --- 处理并重命名 ---
        for node_type, data in current_nodes:
            try:
                proxy_info = {}
                host = ""
                original_uri = ""

                if node_type == 'uri':
                    original_uri = data
                    scheme, rest = data.split('://', 1)
                    scheme = scheme.lower()
                    
                    if scheme == 'vmess':
                        v_json = safe_base64_decode(rest)
                        v_data = json.loads(v_json)
                        host = v_data.get('add')
                        proxy_info = {
                            "type": "vmess", "server": host, "port": int(v_data.get('port', 443)),
                            "uuid": v_data.get('id'), "alterId": int(v_data.get('aid', 0)),
                            "cipher": "auto", "tls": True if v_data.get('tls') == "tls" else False,
                            "network": v_data.get('net', 'tcp'), "servername": v_data.get('sni', ''), "udp": True
                        }
                        if v_data.get('net') in ['ws', 'grpc']:
                            proxy_info[f"{v_data['net']}-opts"] = {"path": v_data.get('path', '/'), "headers": {"Host": v_data.get('host', '')}}
                    else:
                        core = rest.split('#')[0]
                        match = re.search(r'^(?P<user>.*)@(?P<host>[^:/?]+):(?P<port>\d+)', core)
                        if not match: continue
                        host = match.group('host')
                        user = unquote(match.group('user'))
                        proxy_info = {"server": host, "port": int(match.group('port')), "udp": True}
                        query = {k: v[0] for k, v in parse_qs(core.split('?')[1]).items()} if '?' in core else {}
                        
                        if scheme == 'vless':
                            proxy_info.update({"type": "vless", "uuid": user, "tls": True if query.get('security') in ['tls', 'reality'] else False, "flow": query.get('flow', ''), "servername": query.get('sni', '')})
                            if query.get('type') == 'ws': proxy_info.update({"network": "ws", "ws-opts": {"path": query.get('path', '/'), "headers": {"Host": query.get('host', '')}}})
                        elif scheme == 'trojan':
                            proxy_info.update({"type": "trojan", "password": user, "sni": query.get('sni', '')})
                        elif scheme in ['ss', 'shadowsocks']:
                            proxy_info["type"] = "ss"
                            if ':' in user: proxy_info["cipher"], proxy_info["password"] = user.split(':', 1)
                        elif scheme in ['hysteria2', 'hy2']:
                            proxy_info.update({"type": "hysteria2", "password": user, "sni": query.get('sni', ''), "alpn": ["h3"]})
                
                elif node_type == 'clash_obj':
                    proxy_info = data
                    host = data.get('server')
                    # 构造一个虚拟 URI 用于 MD5
                    original_uri = f"{data.get('type')}://{host}:{data.get('port')}"

                if not host: continue
                
                # --- 定位与更名 ---
                index = len(final_uris)
                country = get_country(host, reader)
                md5_tag = get_md5(original_uri + str(index))
                new_name = f"{country}_{index + 1}_{md5_tag}"
                
                proxy_info["name"] = new_name
                clash_proxies.append(proxy_info)
                
                if node_type == 'uri':
                    final_uris.append(f"{data.split('#')[0]}#{new_name}")
                else:
                    # YAML 转换回 URI 简化处理，仅供 nodes.txt 展示
                    final_uris.append(f"{proxy_info['type']}://{host}:{proxy_info['port']}#{new_name}")

            except: continue

    reader.close()

    # --- 写入文件 ---
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"任务完成！总计提取节点: {len(final_uris)}")

if __name__ == "__main__":
    parse_and_rename()
