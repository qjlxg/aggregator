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
    # 用户要求：文件已在根目录，此函数保持结构但不执行下载逻辑
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"错误: 根目录未找到 {GEOIP_DB_PATH}")

def get_country(host, reader):
    try:
        ip = host
        # 如果是域名则解析IP
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
        # 处理补丁和非URL安全字符
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
    return re.findall(pattern, content)

def fetch_content(url):
    try:
        resp = requests.get(url, timeout=15)
        text = resp.text
        # 尝试解码整个订阅内容
        decoded = safe_base64_decode(text)
        return decoded if "://" in decoded else text
    except Exception as e:
        print(f"提取失败: {e}")
        return ""

def parse_and_rename():
    download_geoip()
    raw_data = fetch_content(LINK)
    if not raw_data:
        print("未获取到任何数据")
        return

    uris = extract_nodes(raw_data)
    if not os.path.exists(GEOIP_DB_PATH):
        print("GeoIP 数据库不存在，停止运行")
        return
        
    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    
    clash_proxies = []
    final_uris = []
    
    for index, uri in enumerate(uris):
        try:
            scheme = uri.split('://')[0].lower()
            content = uri.split('://')[1]
            
            # 基础解析变量
            proxy_info = {}
            host = ""
            
            # --- 协议解析逻辑 ---
            if scheme == 'vmess':
                v2_data = json.loads(safe_base64_decode(content))
                host = v2_data.get('add')
                proxy_info = {
                    "type": "vmess", "server": host, "port": int(v2_data.get('port', 443)),
                    "uuid": v2_data.get('id'), "alterId": int(v2_data.get('aid', 0)),
                    "cipher": "auto", "tls": True if v2_data.get('tls') == "tls" else False,
                    "network": v2_data.get('net', 'tcp'), "servername": v2_data.get('sni', ''),
                    "udp": True
                }
                if v2_data.get('net') in ['ws', 'grpc']:
                    opt_key = f"{v2_data['net']}-opts"
                    proxy_info[opt_key] = {"path": v2_data.get('path', '/'), "headers": {"Host": v2_data.get('host', '')}}

            elif scheme in ['vless', 'trojan', 'ss', 'shadowsocks', 'hysteria2', 'hy2', 'tuic', 'snell', 'socks']:
                # 解析 URL 结构
                url_part = uri
                if scheme == 'shadowsocks': url_part = uri.replace('shadowsocks', 'ss')
                parsed = urlparse(url_part)
                host = parsed.hostname
                
                # 基础信息
                proxy_info = {
                    "type": scheme if scheme not in ['hy2', 'shadowsocks'] else ('hysteria2' if scheme=='hy2' else 'ss'),
                    "server": host, "port": parsed.port or 443, "udp": True
                }
                
                # 提取用户认证
                userinfo = unquote(parsed.netloc.split('@')[0]) if '@' in parsed.netloc else ""
                if scheme == 'vless':
                    proxy_info.update({"uuid": userinfo, "tls": True})
                elif scheme in ['trojan', 'hysteria2', 'hy2']:
                    proxy_info.update({"password": userinfo, "tls": True})
                elif scheme == 'ss':
                    if ':' in userinfo:
                        proxy_info["cipher"], proxy_info["password"] = userinfo.split(':', 1)
                elif scheme == 'tuic':
                    proxy_info.update({"uuid": userinfo.split(':')[0], "password": userinfo.split(':')[1] if ':' in userinfo else "", "alpn": ["h3"]})
                
                # 参数处理 (sni, flow, etc.)
                params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if 'sni' in params: proxy_info['servername'] = params['sni']
                if 'flow' in params: proxy_info['flow'] = params['flow']
                if 'path' in params: 
                    proxy_info['network'] = 'ws'
                    proxy_info['ws-opts'] = {'path': params['path']}

            # --- 定位与更名 ---
            if not host: continue
            country = get_country(host, reader)
            md5_suffix = get_md5(uri + str(index))
            new_name = f"{country}_{index + 1}_{md5_suffix}"
            
            # 更新名称
            proxy_info["name"] = new_name
            clash_proxies.append(proxy_info)
            
            # 处理节点列表中的 URI 备注
            base_uri = uri.split('#')[0]
            final_uris.append(f"{base_uri}#{new_name}")

        except Exception as e:
            print(f"解析节点 {index} 出错: {e}")
            continue

    reader.close()

    # 写入文件
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
