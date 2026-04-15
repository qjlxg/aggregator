import os, requests, base64, re, socket, maxminddb, concurrent.futures, json, yaml, hashlib, time, functools
from urllib.parse import urlparse, unquote, quote
from datetime import datetime

# ================= 配置区 =================
CLASH_BASE_CONFIG = {
    "port": 7890,
    "socks-port": 7891,
    "allow-lan": True,
    "mode": "Rule",
    "log-level": "info",
    "external-controller": ":9090",
    "dns": {
        "enable": True,
        "enhanced-mode": "fake-ip",
        "nameserver": ["119.29.29.29", "223.5.5.5"],
        "fallback": ["8.8.8.8", "8.8.4.4", "1.1.1.1", "tls://1.0.0.1:853", "tls://dns.google:853"]
    }
}

@functools.lru_cache(maxsize=2048)
def get_ip(hostname):
    try: return socket.gethostbyname(hostname)
    except: return None

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

def get_short_id(text):
    return hashlib.md5(str(text).encode()).hexdigest()[:4]

def clash_to_uri(node):
    """将 Clash 节点字典转回 URI 字符串 (新增 TUIC/SSR 支持)"""
    try:
        t = node.get('type')
        name = quote(node.get('name', 'node'))
        server = node.get('server')
        port = node.get('port')
        
        if t == 'tuic':
            return f"tuic://{node.get('uuid')}@{server}:{port}?sni={node.get('sni', '')}&version=5#{name}"
        
        if t == 'ssr':
            # 格式: server:port:protocol:method:obfs:b64pass/?obfsparam=...
            pass_b64 = base64.b64encode(node.get('password', '').encode()).decode().replace('=', '')
            main_part = f"{server}:{port}:{node.get('protocol')}:{node.get('cipher')}:{node.get('obfs')}:{pass_b64}"
            return f"ssr://{base64.b64encode(main_part.encode()).decode().replace('=', '')}#{name}"

        if node.get('original_scheme') == 'anytls':
            query = f"insecure={'1' if node.get('skip-cert-verify') else '0'}&sni={node.get('servername', node.get('sni', ''))}"
            return f"anytls://{node.get('uuid', node.get('password'))}@{server}:{port}/?{query}#{name}"
            
        if t == 'ss':
            auth = base64.b64encode(f"{node.get('cipher')}:{node.get('password')}".encode()).decode()
            return f"ss://{auth}@{server}:{port}#{name}"
        elif t == 'vmess':
            v2 = {
                "v": "2", "ps": node.get('name'), "add": server, "port": port,
                "id": node.get('uuid'), "aid": node.get('alterId', 0), "scy": "auto",
                "net": node.get('network', 'tcp'), "type": "none", "host": "", "path": "", "tls": "tls" if node.get('tls') else ""
            }
            if node.get('network') == 'ws':
                v2["path"] = node.get('ws-opts', {}).get('path', '/')
                v2["host"] = node.get('ws-opts', {}).get('headers', {}).get('Host', '')
            v2_json = base64.b64encode(json.dumps(v2).encode()).decode()
            return f"vmess://{v2_json}"
        elif t == 'vless':
            query = f"type={node.get('network', 'tcp')}&security={'tls' if node.get('tls') else 'none'}&sni={node.get('servername', '')}"
            return f"vless://{node.get('uuid')}@{server}:{port}?{query}#{name}"
        elif t == 'trojan':
            return f"trojan://{node.get('password')}@{server}:{port}?sni={node.get('sni', '')}#{name}"
        elif t == 'hysteria2':
            return f"hysteria2://{node.get('password')}@{server}:{port}#{name}"
    except: pass
    return None

def parse_uri_to_clash(uri):
    """将 URI 字符串解析为 Clash 节点字典 (完善版)"""
    if isinstance(uri, dict): return uri
    try:
        if "://" not in uri: return None
        parts = uri.split('#')
        base_uri, tag = parts[0], unquote(parts[1]) if len(parts) > 1 else "Node"
        parsed = urlparse(base_uri)
        
        # SSR 特殊处理 (SSR 往往不遵循标准 URL 格式)
        if parsed.scheme == 'ssr':
            raw = decode_base64(base_uri.replace("ssr://", ""))
            main_parts = raw.split(':')
            if len(main_parts) >= 6:
                return {
                    "name": tag, "type": "ssr", "server": main_parts[0], "port": int(main_parts[1]),
                    "protocol": main_parts[2], "cipher": main_parts[3], "obfs": main_parts[4],
                    "password": decode_base64(main_parts[5].split('/')[0]), "udp": True
                }
        
        if not parsed.hostname: return None
        node = {"name": tag, "server": parsed.hostname, "port": int(parsed.port or 443), "udp": True}
        node['original_scheme'] = parsed.scheme
        query = {k.lower(): unquote(v) for k, v in [p.split('=', 1) for p in parsed.query.split('&') if '=' in p]} if parsed.query else {}
        
        if parsed.scheme == 'tuic':
            node.update({
                "type": "tuic", "uuid": parsed.username, "password": parsed.password,
                "sni": query.get('sni'), "alpn": ["h3"], "congestion-controller": "bbr",
                "skip-cert-verify": True
            })
            return node
        elif parsed.scheme == 'anytls':
            node.update({"type": "vless", "uuid": parsed.username, "tls": True, "servername": query.get('sni'), "skip-cert-verify": query.get('insecure') == '1'})
            return node
        elif parsed.scheme == 'ss':
            auth = decode_base64(parsed.netloc.split('@')[0])
            if ':' in auth:
                node.update({"type": "ss", "cipher": auth.split(':')[0], "password": auth.split(':')[1]})
                return node
        elif parsed.scheme == 'vmess':
            v2_json = decode_base64(base_uri.replace("vmess://", ""))
            v2 = json.loads(v2_json)
            node.update({"type": "vmess", "uuid": v2.get('id'), "alterId": int(v2.get('aid', 0)), "cipher": "auto", "tls": v2.get('tls') in ["tls", True], "network": v2.get('net', 'tcp')})
            if node["network"] == 'ws': node["ws-opts"] = {"path": v2.get('path', '/'), "headers": {"Host": v2.get('host', '')}}
            return node
        elif parsed.scheme == 'vless':
            node.update({"type": "vless", "uuid": parsed.username, "tls": query.get('security') in ['tls', 'reality'], "servername": query.get('sni'), "network": query.get('type', 'tcp')})
            if query.get('security') == 'reality': node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
            return node
        elif parsed.scheme in ['hysteria2', 'hy2']:
            node.update({"type": "hysteria2", "password": parsed.username or query.get('auth'), "sni": query.get('sni'), "skip-cert-verify": True})
            return node
        elif parsed.scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": query.get('sni'), "skip-cert-verify": True})
            return node
    except: return None
    return None

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        if "proxies:" in content:
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict) and 'proxies' in data: return data['proxies']
            except: pass
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:anytls|vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except: return []

def process_node_full(item, reader):
    node = parse_uri_to_clash(item)
    if not node: return None
    server = node.get('server')
    nid = f"{server}:{node.get('port')}:{node.get('type')}"
    ip = get_ip(server)
    c_name, flag = "未知地区", "🌐"
    if ip and reader:
        try:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                c_name = names.get('zh-CN', names.get('en', "未知地区"))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        except: pass
    sid = get_short_id(nid)
    node['name'] = f"{flag} {c_name} 打倒美帝国主义及其一切走狗_{sid}"
    uri = clash_to_uri(node)
    return nid, node, uri

def main():
    DATA_PATH = os.getenv('DATA_PATH', 'private_folder/data')
    INPUT_FILE = os.path.join(DATA_PATH, 'sub_parser.txt')
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    
    links, raw_nodes = [], []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.startswith('http'): links.append(line)
                elif '://' in line: raw_nodes.append(line)
        print(f"--- Info: Loaded {len(links)} links and {len(raw_nodes)} nodes from file ---")

    link_env = os.environ.get('LINK', '').strip()
    if link_env:
        for l in link_env.split('\n'):
            l = l.strip()
            if not l: continue
            if l.startswith('http'): links.append(l)
            elif '://' in l: raw_nodes.append(l)

    links = list(set(links))
    raw_items = []
    if links:
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(fetch_source, links))
            for r in results: raw_items.extend(r)
    raw_items.extend(raw_nodes)

    if not raw_items:
        print("No nodes found. Exiting.")
        return

    mmdb_path = 'GeoLite2-Country.mmdb'
    reader = maxminddb.open_database(mmdb_path) if os.path.exists(mmdb_path) else None
    
    final_proxies, final_uris, seen_nodes = [], [], set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(process_node_full, item, reader) for item in raw_items]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                nid, clash_node, uri = res
                if nid not in seen_nodes:
                    seen_nodes.add(nid)
                    clean_clash = {k: v for k, v in clash_node.items() if k != 'original_scheme'}
                    final_proxies.append(clean_clash)
                    if uri: final_uris.append(uri)
    if reader: reader.close()

    output_dir = 'data'
    os.makedirs(output_dir, exist_ok=True)
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    p_names = [p['name'] for p in final_proxies]
    
    full_config = CLASH_BASE_CONFIG.copy()
    full_config.update({
        "proxies": final_proxies,
        "proxy-groups": [
            {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + p_names},
            {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": p_names}
        ],
        "rules": ["MATCH,🔰 节点选择"]
    })

    # 写入文件
    with open(os.path.join(output_dir, 'clash.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'# Last Updated: {update_time}\n# Total: {len(final_proxies)}\n\n')
        yaml.safe_dump(full_config, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(output_dir, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write("\n".join(final_uris))
    
    b64_content = base64.b64encode(("\n".join(final_uris)).encode('utf-8')).decode('utf-8')
    with open(os.path.join(output_dir, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)
    
    print(f"--- Done | Unique Nodes: {len(final_proxies)} ---")

if __name__ == "__main__":
    main()
