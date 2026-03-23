import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml
from urllib.parse import urlparse, unquote
from datetime import datetime

def get_flag(code):
    if not code: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def decode_base64(data):
    if not data: return ""
    try:
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

def get_ip(hostname):
    try: return socket.gethostbyname(hostname)
    except: return None

def parse_uri_to_clash(uri):
    try:
        parts = uri.split('#')
        tag = unquote(parts[1]) if len(parts) > 1 else "Unnamed_Node"
        base_uri = parts[0]
        parsed = urlparse(base_uri)
        scheme = parsed.scheme.lower()
        node = {"name": tag, "server": parsed.hostname, "port": parsed.port or 443, "udp": True}
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
                else:
                    user_info = decode_base64(parsed.username + "==").split(':', 1)
                    method, password = user_info[0], user_info[1]
                node.update({"type": "ss", "cipher": method, "password": password})
            return node
        elif scheme == 'ssr':
            ssr_raw = decode_base64(base_uri.replace("ssr://", ""))
            main_part, param_part = ssr_raw.split('/?', 1) if '/?' in ssr_raw else (ssr_raw, "")
            m = main_part.split(':')
            if len(m) >= 6:
                node.update({"type": "ssr", "server": m[0], "port": int(m[1]), "protocol": m[2], "cipher": m[3], "obfs": m[4], "password": decode_base64(m[5])})
            return node
        elif scheme == 'vmess':
            v2_json = json.loads(decode_base64(base_uri.replace("vmess://", "")))
            node.update({"type": "vmess", "uuid": v2_json.get('id'), "alterId": int(v2_json.get('aid', 0)), "cipher": "auto", "tls": v2_json.get('tls') in ["tls", True], "network": v2_json.get('net', 'tcp')})
            if node["network"] == 'ws': node["ws-opts"] = {"path": v2_json.get('path', '/'), "headers": {"Host": v2_json.get('host', '')}}
            elif node["network"] == 'grpc': node["grpc-opts"] = {"grpc-service-name": v2_json.get('path', '')}
            return node
        elif scheme == 'vless':
            node.update({"type": "vless", "uuid": parsed.username, "tls": query.get('security') in ['tls', 'reality'], "servername": query.get('sni') or query.get('peer'), "network": query.get('type', 'tcp')})
            if query.get('security') == 'reality':
                node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
                node["client-fingerprint"] = query.get('fp', 'chrome')
            if node["network"] == 'ws': node["ws-opts"] = {"path": query.get('path', '/'), "headers": {"Host": query.get('host', '')}}
            elif node["network"] == 'grpc': node["grpc-opts"] = {"grpc-service-name": query.get('serviceName', query.get('service', ''))}
            return node
        elif scheme in ['hysteria2', 'hy2']:
            node.update({"type": "hysteria2", "password": parsed.username or query.get('auth'), "sni": query.get('sni'), "skip-cert-verify": True})
            return node
        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": query.get('sni') or parsed.hostname, "skip-cert-verify": True})
            return node
        elif scheme == 'tuic':
            node.update({"type": "tuic", "uuid": parsed.username, "password": parsed.password, "sni": query.get('sni'), "alpn": [query.get('alpn', 'h3')]})
            return node
    except: return None
    return None

def rename_node(uri, reader):
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        ip = get_ip(parsed.hostname)
        country, flag = "Unknown", "🌐"
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        return f"{base_uri}#{flag} {country} | 省点用"
    except: return uri

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except: return []

def main():
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links: return

    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as exc:
        results = list(exc.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as exc:
        final_uris = list(exc.map(lambda u: rename_node(u, reader), unique_uris))
    if reader: reader.close()

    os.makedirs('data', exist_ok=True)
    clash_proxies = []
    for uri in final_uris:
        cfg = parse_uri_to_clash(uri)
        if cfg: clash_proxies.append(cfg)

    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    clash_config = {
        "port": 7890, "socks-port": 7891, "allow-lan": True, "mode": "Rule", "log-level": "info",
        "proxies": clash_proxies,
        "proxy-groups": [
            {"name": "🔰 节点选择", "type": "select", "proxies": ["🎯 全球直连"] + [p['name'] for p in clash_proxies]},
            {"name": "🎯 全球直连", "type": "select", "proxies": ["DIRECT", "🔰 节点选择"]}
        ],
        "rules": ["MATCH,🔰 节点选择"]
    }

    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write(f"# Generated at: {update_time}\n")
        yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

if __name__ == "__main__":
    main()
