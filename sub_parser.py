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
from concurrent.futures import ThreadPoolExecutor  # 引入并发库

# 配置
LINK = os.environ.get('LINK', '')
OUTPUT_DIR = 'data'
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"

# 确保输出目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 全局 DNS 缓存，避免重复解析同一域名导致卡死
DNS_CACHE = {}

def get_country_flag(host, reader):
    try:
        if not reader:
            return "🏳️"
        
        # 检查是否已经是 IP 地址
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            ip = host
        else:
            # 引入缓存逻辑与超时控制
            if host in DNS_CACHE:
                ip = DNS_CACHE[host]
            else:
                # 设置全局 socket 超时为 3 秒，防止单个域名解析卡死
                socket.setdefaulttimeout(3)
                try:
                    ip = socket.gethostbyname(host)
                    DNS_CACHE[host] = ip
                except:
                    return "🏳️"
        
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
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except Exception:
        return ""

def extract_nodes(content):
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content, re.IGNORECASE)

def fetch_content(url):
    if not url: return ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # 针对并发，缩短超时到 10 秒更合理
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text.strip()
        if "://" not in text and "proxies:" not in text:
            decoded = safe_base64_decode(text)
            if "://" in decoded: return decoded
        return text
    except Exception as e:
        print(f"Fetch Content Error ({url}): {e}")
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

    # --- 1. 使用并发线程池下载所有 URL ---
    # max_workers=20 表示同时下载 20 个链接
    fetched_results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        fetched_results = list(executor.map(fetch_content, urls))
    
    # --- 2. 顺序解析下载回来的内容 ---
    for raw_data in fetched_results:
        if not raw_data: continue

        current_nodes = []
        # --- 识别 YAML 格式 ---
        if "proxies:" in raw_data:
            try:
                y_data = yaml.safe_load(raw_data)
                if y_data and 'proxies' in y_data:
                    for p in y_data['proxies']:
                        current_nodes.append(('clash_obj', p))
            except Exception: pass
        
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
                    parsed_url = urlparse(data)
                    scheme = parsed_url.scheme.lower()
                    
                    if scheme == 'vmess':
                        v_json = safe_base64_decode(data.split('://', 1)[1])
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
                                if query.get('fp'): proxy_info['client-fingerprint'] = query.get('fp')
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
                                plugin_opts = {}
                                for kv in query.get('plugin').split(';')[1:]:
                                    if '=' in kv:
                                        k, v = kv.split('=', 1)
                                        plugin_opts[k] = v
                                proxy_info['plugin-opts'] = plugin_opts
                                
                        elif scheme in ['hysteria2', 'hy2']:
                            proxy_info.update({"type": "hysteria2", "password": user, "sni": query.get('sni', ''), "alpn": ["h3"]})
                
                elif node_type == 'clash_obj':
                    proxy_info = data
                    host = data.get('server')
                    original_uri = f"{data.get('type')}://{host}:{data.get('port')}"

                if not host: continue
                
                # --- 定位与更名 (国旗+MD5) ---
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

    # --- 写入文件 ---
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proxy_names = [p['name'] for p in clash_proxies]
    
    # 策略组逻辑优化：只有当存在节点时才创建完整的策略组
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
                "proxies": (["⚡ 自动选择", "DIRECT"] + proxy_names) if proxy_names else ["DIRECT"]
            },
            {
                "name": "⚡ 自动选择",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names if proxy_names else ["DIRECT"]
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
