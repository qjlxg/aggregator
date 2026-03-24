import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml
from urllib.parse import urlparse, unquote
from datetime import datetime

# ================= 配置区 =================
MY_SIGNATURE = "🔋 搬砖专用通道 (每月一更)"
MY_REMARK = "|每月一更"
SLOGAN_1 = "节点虽多，请且用且珍惜"
SLOGAN_2 = "正在连接到月球背面..."
# ==========================================

def get_flag(code):
    if not code: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def decode_base64(data):
    if not data: return ""
    try:
        data = data.replace("-", "+").replace("_", "/")
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

def get_ip(hostname):
    try: return socket.gethostbyname(hostname)
    except: return None

def parse_uri_to_clash(uri):
    """全功能解析引擎：支持 SS, VMess, VLESS, Trojan, Hy2, TUIC, Socks"""
    try:
        if "://" not in uri: return None
        parts = uri.split('#')
        base_uri = parts[0]
        raw_tag = unquote(parts[1]) if len(parts) > 1 else "Unnamed_Node"
        tag = re.sub(r'[\"\'\[\]\{\}\>\<\#]', '', raw_tag).strip()
        
        parsed = urlparse(base_uri)
        scheme = parsed.scheme.lower()
        node = {"name": tag, "server": parsed.hostname, "port": int(parsed.port or 443), "udp": True}
        
        query = {}
        if parsed.query:
            for pair in parsed.query.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    query[k.lower()] = unquote(v)

        if scheme == 'ss':
            if '@' in parsed.netloc:
                auth_part = parsed.netloc.split('@')[0]
                auth_decoded = decode_base64(auth_part)
                if ':' in auth_decoded:
                    method, password = auth_decoded.split(':', 1)
                    node.update({"type": "ss", "cipher": method, "password": password})
            return node
        
        elif scheme == 'vmess':
            try:
                v2_json = json.loads(decode_base64(base_uri.replace("vmess://", "")))
                node.update({
                    "type": "vmess", "uuid": v2_json.get('id'), 
                    "alterId": int(v2_json.get('aid', 0)), "cipher": "auto", 
                    "tls": v2_json.get('tls') in ["tls", True], 
                    "network": v2_json.get('net', 'tcp')
                })
                if node["network"] == 'ws': 
                    node["ws-opts"] = {"path": v2_json.get('path', '/'), "headers": {"Host": v2_json.get('host', '')}}
                elif node["network"] == 'grpc':
                    node["grpc-opts"] = {"grpc-service-name": v2_json.get('path', '')}
                return node
            except: return None
            
        elif scheme == 'vless':
            node.update({
                "type": "vless", "uuid": parsed.username, 
                "tls": query.get('security') in ['tls', 'reality'], 
                "servername": query.get('sni'), "network": query.get('type', 'tcp')
            })
            if query.get('security') == 'reality':
                node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
            if query.get('flow'): node["flow"] = query.get('flow')
            if query.get('type') == 'grpc':
                node["grpc-opts"] = {"grpc-service-name": query.get('serviceName', '')}
            return node
            
        elif scheme in ['hysteria2', 'hy2']:
            node.update({
                "type": "hysteria2", "password": parsed.username or query.get('auth'), 
                "sni": query.get('sni'), "skip-cert-verify": True
            })
            return node
            
        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": query.get('sni'), "skip-cert-verify": True})
            return node

        elif scheme == 'tuic':
            node.update({
                "type": "tuic", "uuid": parsed.username, "password": parsed.password,
                "sni": query.get('sni'), "alpn": [query.get('alpn', 'h3')], "skip-cert-verify": True
            })
            return node

        elif scheme == 'socks':
            node.update({"type": "socks5", "username": parsed.username, "password": parsed.password})
            return node

    except: return None
    return None

def rename_node(uri, reader):
    try:
        if "#" not in uri: return uri
        base_uri, original_tag = uri.split('#', 1)
        original_tag = unquote(original_tag)
        if any(x in original_tag for x in ["剩余流量", "过期时间", "重置", "GB"]): return uri

        parsed = urlparse(base_uri)
        ip = get_ip(parsed.hostname)
        country_name, flag = "", ""
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        
        display_name = country_name if country_name else original_tag
        display_flag = flag if flag else "🌐"
        return f"{base_uri}#{display_flag} {display_name} {MY_REMARK}"
    except: return uri

def fetch_source(url_info):
    idx, url = url_info
   
    domain_peek = urlparse(url).netloc[:3] + "..."
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        nodes = re.findall(r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+', content, re.IGNORECASE)
        print(f"DEBUG: Source [{idx}] ({domain_peek}) fetched {len(nodes)} nodes.")
        return nodes
    except:
        print(f"DEBUG: Source [{idx}] ({domain_peek}) request failed.")
        return []

def main():
    link_env = os.environ.get('LINK', '').strip()
    if not link_env: return

   
    for line in link_env.split('\n'):
        if line.strip(): print(f"::add-mask::{line.strip()}")

    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    all_uris = []
    link_tasks = list(enumerate(links))

    print(f"🚀 Starting to fetch from {len(links)} sources...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, link_tasks))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        final_nodes_uris = list(executor.map(lambda u: rename_node(u, reader), unique_uris))
    if reader: reader.close()

    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))

    clash_proxies = []
    name_counter = {}
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg:
            base_name = node_cfg['name']
            if base_name in name_counter:
                name_counter[base_name] += 1
                node_cfg['name'] = f"{base_name} {name_counter[base_name]}"
            else:
                name_counter[base_name] = 0
            clash_proxies.append(node_cfg)

    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write(f"# subscription-userinfo: upload=0; download=0; total=1073741824000000; expire=4070880000\n")
        f.write(f'# profile-title: "{MY_SIGNATURE}"\n')
        f.write(f"# {SLOGAN_1} | {SLOGAN_2}\n\n")
        
        config = {
            "port": 7890, "socks-port": 7891, "allow-lan": True, "mode": "rule",
            "proxies": clash_proxies,
            "proxy-groups": [
                {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + [p['name'] for p in clash_proxies]},
                {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": [p['name'] for p in clash_proxies]}
            ],
            "rules": ["MATCH,🔰 节点选择"]
        }
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"✨ Success! Total valid nodes: {len(clash_proxies)}")

if __name__ == "__main__":
    main()
