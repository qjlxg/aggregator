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
from concurrent.futures import ThreadPoolExecutor

LINK = os.environ.get('LINK', '')
OUTPUT_DIR = 'data'
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

DNS_CACHE = {}

def mask_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc
        if not host:
            return "***"
        if len(host) > 4:
            return f"{host[:2]}***{host[-4:]}"
        return "***"
    except:
        return "***"

def get_country_flag(host, reader):
    try:
        if not reader:
            return "🏳️"
        
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            ip = host
        else:
            if host in DNS_CACHE:
                ip = DNS_CACHE[host]
            else:
                socket.setdefaulttimeout(3)
                ip = socket.gethostbyname(host)
                DNS_CACHE[host] = ip
        
        response = reader.country(ip)
        code = response.country.iso_code
        if code:
            return "".join(chr(127397 + ord(c)) for c in code.upper())
        return "🏳️"
    except Exception:
        return "🏳️"

def get_md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:5]

def safe_base64_decode(s):
    try:
        # 处理 URL-safe base64 字符
        s = s.replace('-', '+').replace('_', '/')
        # 移除所有非 base64 标准字符（如换行、空格等）
        s = re.sub(r'[^a-zA-Z0-9+/]', '', s)
        
        # Base64 长度规律：不能是 4n+1。如果是 4n+1，说明最后一个字符是多余的或者是噪声
        if len(s) % 4 == 1:
            s = s[:-1]
            
        # 补齐填充符
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
            
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except Exception as e:
        # 打印错误时包含简短摘要，避免刷屏
        print(f"Base64 Decode Error: {str(e)}")
        return ""

def extract_nodes(content):
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content, re.IGNORECASE)

def fetch_content(url):
    if not url: return ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text.strip()
        # 如果不是明显的节点列表或 Clash 配置，尝试 Base64 解码
        if "://" not in text and "proxies:" not in text:
            decoded = safe_base64_decode(text)
            if "://" in decoded: return decoded
        return text
    except Exception:
        print(f"Fetch Content Error for [{mask_url(url)}]: Connection Failed")
        return ""

def parse_and_rename():
    urls = re.split(r'[,\s]+', LINK.strip())
    
    reader = None
    try:
        if os.path.exists(GEOIP_DB_PATH):
            reader = geoip2.database.Reader(GEOIP_DB_PATH)
    except Exception as e:
        print(f"GeoIP Reader Init Error: {e}")

    clash_proxies = []
    final_uris = []

    fetched_results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        fetched_results = list(executor.map(fetch_content, urls))
    
    for raw_data in fetched_results:
        if not raw_data: continue

        current_nodes = []
        # 处理 Clash YAML 格式
        if "proxies:" in raw_data:
            try:
                y_data = yaml.safe_load(raw_data)
                if y_data and 'proxies' in y_data:
                    for p in y_data['proxies']:
                        current_nodes.append(('clash_obj', p))
            except Exception as e:
                print(f"YAML Parse Error: {e}")
        
        # 处理 URI 格式
        uris = extract_nodes(raw_data)
        for u in uris:
            current_nodes.append(('uri', u))

        for node_type, data in current_nodes:
            try:
                proxy_info = {}
                host = ""
                original_uri = ""

                if node_type == 'uri':
                    original_uri = data
                    parsed_url = urlparse(data)
                    scheme = parsed_url.scheme.lower()
                    
                    if scheme == 'vmess':
                        v_json = safe_base64_decode(data.split('://', 1)[1])
                        if not v_json: continue
                        v_data = json.loads(v_json)
                        host = v_data.get('add')
                        proxy_info = {
                            "name": "", "type": "vmess", "server": host, "port": int(v_data.get('port', 443)),
                            "uuid": v_data.get('id'), "alterId": int(v_data.get('aid', 0)),
                            "cipher": "auto", "tls": True if v_data.get('tls') == "tls" else False,
                            "network": v_data.get('net', 'tcp'), "servername": v_data.get('sni', ''), "udp": True
                        }
                        if v_data.get('net') in ['ws', 'grpc']:
                            proxy_info[f"{v_data['net']}-opts"] = {"path": v_data.get('path', '/'), "headers": {"Host": v_data.get('host', '')}}
                    
                    else:
                        core = data.split('#')[0]
                        match = re.search(r'^(?P<scheme>.*)://(?P<userinfo>.*)@(?P<host>[^:/?#]+):(?P<port>\d+)', core)
                        if not match: continue
                        
                        host = match.group('host')
                        user = unquote(match.group('userinfo'))
                        proxy_info = {"name": "", "server": host, "port": int(match.group('port')), "udp": True}
                        
                        query_part = core.split('?')[1] if '?' in core else ""
                        query = {k: v[0] for k, v in parse_qs(query_part).items()}
                        
                        if scheme == 'vless':
                            proxy_info.update({
                                "type": "vless", "uuid": user, 
                                "tls": True if query.get('security') in ['tls', 'reality'] else False,
                                "flow": query.get('flow', ''), "servername": query.get('sni', '')
                            })
                            if query.get('security') == 'reality':
                                proxy_info['reality-opts'] = {"public-key": query.get('pbk', ''), "short-id": query.get('sid', '')}
                            if query.get('type') == 'ws': 
                                proxy_info.update({"network": "ws", "ws-opts": {"path": query.get('path', '/'), "headers": {"Host": query.get('host', '')}}})
                        
                        elif scheme == 'trojan':
                            proxy_info.update({"type": "trojan", "password": user, "sni": query.get('sni', '')})
                        
                        elif scheme in ['ss', 'shadowsocks']:
                            proxy_info["type"] = "ss"
                            if ':' in user: 
                                proxy_info["cipher"], proxy_info["password"] = user.split(':', 1)
                            else: 
                                proxy_info["cipher"], proxy_info["password"] = "auto", user
                            if query.get('plugin'):
                                proxy_info['plugin'] = query.get('plugin').split(';')[0]
                                proxy_info['plugin-opts'] = {kv.split('=')[0]: kv.split('=')[1] for kv in query.get('plugin').split(';')[1:] if '=' in kv}
                                
                        elif scheme in ['hysteria2', 'hy2']:
                            proxy_info.update({"type": "hysteria2", "password": user, "sni": query.get('sni', ''), "alpn": ["h3"]})
                
                elif node_type == 'clash_obj':
                    proxy_info = data
                    host = data.get('server')
                    original_uri = f"{data.get('type')}://{host}:{data.get('port')}"

                if not host: continue
                
                index = len(final_uris)
                flag = get_country_flag(host, reader)
                md5_tag = get_md5(original_uri + str(index))
                new_name = f"{flag}_{md5_tag}"
                
                proxy_info["name"] = new_name
                clash_proxies.append(proxy_info)
                
                if node_type == 'uri':
                    final_uris.append(f"{data.split('#')[0]}#{new_name}")
                else:
                    final_uris.append(f"{proxy_info['type']}://{host}:{proxy_info['port']}#{new_name}")

            except Exception:
                continue

    if reader:
        reader.close()

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proxy_names = [p['name'] for p in clash_proxies]
    
    clash_full_config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "proxies": clash_proxies,
        "proxy-groups": [
            {
                "name": "🚀 节点选择",
                "type": "select",
                "proxies": ["⚡ 自动选择", "DIRECT"] + proxy_names
            },
            {
                "name": "⚡ 自动选择",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names
            }
        ],
        "rules": [
            "MATCH,🚀 节点选择"
        ]
    }

    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump(clash_full_config, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"任务完成！总计提取节点: {len(final_uris)}")

if __name__ == "__main__":
    parse_and_rename()
