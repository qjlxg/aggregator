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
GEOIP_DB_PATH = "GeoLite2-Country.mm = v_data.get('add')
                        proxy_info = {
                            "name": "", "type": "vmess", "server": host, "port": int(v_data.get('port', 443)),
                            "uuid": v_data.get('id'), "alterId": int(v_data.get('aid', 0)),
                            "cipher": "auto", "tls": True if vdb"

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
            return f"{host[:2]}***{host[-4_data.get('tls') == "tls" else False,
                            "network": v_data.get('net', 'tcp'), "servername": v_data.get('sni', ''), "udp": True
                        :]}"
        return "***"
    except:
        return "***"

def get_country_flag(host, reader):
}
                        if v_data.get('net') in ['ws', 'grpc']:
                            proxy_info    try:
        if not reader:
            return "🏳️ 未知"
        
        if re.match(r[f"{v_data['net']}-opts"] = {"path": v_data.get('path',"^\d{1,3}(\.\d{1,3}){3}$", host):
            ip = '/'), "headers": {"Host": v_data.get('host', '')}}
                    
                    else: host
        else:
            if host in DNS_CACHE:
                ip = DNS_CACHE[host]
                        core = data.split('#')[0]
                        match = re.search(r'^(?P
            else:
                socket.setdefaulttimeout(3)
                ip = socket.gethostbyname(<scheme>.*)://(?P<userinfo>.*)@(?P<host>[^:/?#host)
                DNS_CACHE[host] = ip
        
        response = reader.country(ip)]+):(?P<port>\d+)', core)
                        if not match: continue
                        
                        host
        code = response.country.iso_code
        # 优先获取中文名，若无则获取 = match.group('host')
                        user = unquote(match.group('userinfo'))
                        proxy英文名
        name = response.country.names.get('zh-CN', response.country.name)_info = {"name": "", "server": host, "port": int(match.group('port')), "udp": True}
                        
                        query_part = core.split('?')[1] if '?' in or "未知"
        if code:
            flag = "".join(chr(127397 + ord(c)) for c in code.upper())
            return f"{flag} {name}"
        return core else ""
                        query = {k: v[0] for k, v in parse_qs(query f"🏳️ {name}"
    except Exception:
        return "🏳️ 未知"

def get__part).items()}
                        
                        if scheme == 'vless':
                            proxy_info.update({md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:5]
                                "type": "vless", "uuid": user, 
                                "tls": True if query.

def safe_base64_decode(s):
    try:
        s = s.replace('-',get('security') in ['tls', 'reality'] else False,
                                "flow": query.get('flow', ''), "servername": query.get('sni', '')
                            })
                            if query.get('security') == 'reality':
                                proxy_info['reality-opts'] = {"public-key": query.get(' '+').replace('_', '/')
        s = re.sub(r'[^a-zA-Z0-pbk', ''), "short-id": query.get('sid', '')}
                            if query.get('type') == 'ws': 
                                proxy_info.update({"network": "ws", "ws-opts9+/]', '', s)
        if len(s) % 4 == 1:
            s =": {"path": query.get('path', '/'), "headers": {"Host": query.get('host', s[:-1]
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode '')}}})
                        
                        elif scheme == 'trojan':
                            proxy_info.update({"type":(s).decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Base64 Decode Error: {e}")
        return ""

def extract_nodes(content):
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria "trojan", "password": user, "sni": query.get('sni', '')})
                        
                        elif scheme in ['ss2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks', 'shadowsocks']:
                            proxy_info["type"] = "ss"
                            if ':' in user: 
                                proxy_info["cipher"], proxy_info["password"] = user.split(':', 1)']
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content, re.IGNORECASE)

def fetch_
                            else: 
                                proxy_info["cipher"], proxy_info["password"] = "auto", usercontent(url):
    if not url: return ""
    try:
        headers = {'User-Agent
                            if query.get('plugin'):
                                proxy_info['plugin'] = query.get('plugin').split(';')[0]
                                proxy_info['plugin-opts'] = {kv.split('=')[0': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)]: kv.split('=')[1] for kv in query.get('plugin').split(';')[1:] if AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout '=' in kv}
                                
                        elif scheme in ['hysteria2', 'hy2']:
                            proxy=10)
        text = resp.text.strip()
        if "://" not in text and "_info.update({"type": "hysteria2", "password": user, "sni": query.get('proxies:" not in text:
            decoded = safe_base64_decode(text)
            ifsni', ''), "alpn": ["h3"]})
                
                elif node_type == 'clash "://" in decoded: return decoded
        return text
    except Exception:
        print(f"Fetch Content_obj':
                    proxy_info = data
                    host = data.get('server')
                    original_ Error for [{mask_url(url)}]: Connection Failed")
        return ""

def parse_and_renameuri = f"{data.get('type')}://{host}:{data.get('port')}"

                if():
    urls = re.split(r'[,\s]+', LINK.strip())
    
    reader not host: continue
                
                index = len(final_uris)
                flag, country_name = get_country = None
    try:
        if os.path.exists(GEOIP_DB_PATH):
            _flag(host, reader)
                md5_tag = get_md5(original_uri + strreader = geoip2.database.Reader(GEOIP_DB_PATH)
    except Exception as e:
        print(f"GeoIP Reader Init Error: {e}")

    clash_proxies = [](index))
                new_name = f"{flag}{country_name}_{md5_tag}"
                
                proxy_info
    final_uris = []

    fetched_results = []
    with ThreadPoolExecutor(max_workers["name"] = new_name
                clash_proxies.append(proxy_info)
                
=20) as executor:
        fetched_results = list(executor.map(fetch_content, urls                if node_type == 'uri':
                    final_uris.append(f"{data.split('#')[))
    
    for raw_data in fetched_results:
        if not raw_data: continue

0]}#{new_name}")
                else:
                    final_uris.append(f"{proxy_info        current_nodes = []
        if "proxies:" in raw_data:
            try:
                ['type']}://{host}:{proxy_info['port']}#{new_name}")

            except Exception:
y_data = yaml.safe_load(raw_data)
                if y_data and 'proxies                continue

    if reader:
        reader.close()

    update_time = datetime.now().strftime' in y_data:
                    for p in y_data['proxies']:
                        current_nodes.append(('clash_obj', p))
            except Exception as e:
                print(f"YAML Parse("%Y-%m-%d %H:%M:%S")
    proxy_names = [p['name'] for p in clash_ Error: {e}")
        
        uris = extract_nodes(raw_data)
        for u inproxies]
    
    clash_full_config = {
        "port": 789 uris:
            current_nodes.append(('uri', u))

        for node_type, data in0,
        "socks-port": 7891,
        "allow-lan": True, current_nodes:
            try:
                proxy_info = {}
                host = ""
                original_uri = ""


        "mode": "rule",
        "log-level": "info",
        "proxies":                if node_type == 'uri':
                    original_uri = data
                    parsed_url = urlparse clash_proxies,
        "proxy-groups": [
            {
                "name": "🚀 (data)
                    scheme = parsed_url.scheme.lower()
                    
                    if scheme == 'vm节点选择",
                "type": "select",
                "proxies": ["⚡ 自动选择", "ess':
                        v_json = safe_base64_decode(data.split('://', 1DIRECT"] + proxy_names
            },
            {
                "name": "⚡ 自动选择",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate)[1])
                        if not v_json: continue
                        v_data = json.loads(v_json)
                        host_204",
                "interval": 300,
                "tolerance": 50, = v_data.get('add')
                        proxy_info = {
                            "name": "", "type
                "proxies": proxy_names
            }
        ],
        "rules": [
            "": "vmess", "server": host, "port": int(v_data.get('port', MATCH,🚀 节点选择"
        ]
    }

    with open(os.path.join(443)),
                            "uuid": v_data.get('id'), "alterId": int(v_data.get('aid', 0)),
                            "cipher": "auto", "tls": True if vOUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        _data.get('tls') == "tls" else False,
                            "network": v_data.getyaml.safe_dump(clash_full_config, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR,('net', 'tcp'), "servername": v_data.get('sni', ''), "udp": True
                         'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f}
                        if v_data.get('net') in ['ws', 'grpc']:
                            proxy_info"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".[f"{v_data['net']}-opts"] = {"path": v_data.get('path',join(final_uris) + "\n")
    
    b64_content = base64. '/'), "headers": {"Host": v_data.get('host', '')}}
                    
                    else:b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).
                        core = data.split('#')[0]
                        match = re.search(r'^(?Pdecode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2<scheme>.*)://(?P<userinfo>.*)@(?P<host>[^:/?#]+):(?P<port>\d+)', core)
                        if not match: continue
                        
                        hostray.txt'), 'w', encoding='utf-8') as f:
        f.write(b6 = match.group('host')
                        user = unquote(match.group('userinfo'))
                        proxy4_content)

    print(f"任务完成！总计提取节点: {len(final_uris)}")

if __name__ == "__main__":
    parse_and_rename()
