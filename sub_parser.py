import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml
from urllib.parse import urlparse, unquote
from datetime import datetime

# ================= 配置区 (严格保留您的参数) =================
MY_SIGNATURE = "🔋 搬砖专用通道 (每月一更)"
MY_REMARK = "|每月一更"
SLOGAN_1 = "节点虽多，请且用且珍惜"
SLOGAN_2 = "正在连接到月球背面..."
# =============================================================

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
    """深度解析引擎 (保持原版逻辑)"""
    try:
        if "://" not in uri: return None
        # 处理不带 # 的情况
        if "#" in uri:
            parts = uri.split('#')
            base_uri = parts[0]
            tag = unquote(parts[1])
        else:
            base_uri = uri
            tag = "Unnamed_Node"
            
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
                    node.update({"type": "ss", "cipher": method, "password": password})
            return node
        elif scheme == 'ssr':
            ssr_raw = decode_base64(base_uri.replace("ssr://", ""))
            m = ssr_raw.split('/?')[0].split(':')
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
    except: return None
    return None

def rename_node(uri, reader):
    try:
        parts = uri.split('#')
        base_uri = parts[0]
        original_tag = unquote(parts[1]) if len(parts) > 1 else "Unknown"
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

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        info = {}
        h = resp.headers.get('Subscription-Userinfo', '')
        if h:
            for item in h.split(';'):
                if '=' in item:
                    k, v = item.split('=', 1)
                    try: info[k.strip().lower()] = int(v.strip())
                    except: pass
            if info.get("total", 0) > 0:
                if (info["total"] - (info.get("upload", 0) + info.get("download", 0))) < (1024**3): return []
        if info.get("expire") and info["expire"] > 0 and int(time.time()) >= info["expire"]: return []
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        return re.findall(r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+', content, re.IGNORECASE)
    except: return []

def main():
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links: return

    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        final_nodes_uris = list(executor.map(lambda u: rename_node(u, reader), unique_uris))
    if reader: reader.close()

    os.makedirs('data', exist_ok=True)

    # 1. nodes.txt (纯净节点列表，不加任何注释，防止 Provider 报错)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))

    # 2. clash.yaml (严格遵循 YAML 规范)
    clash_proxies = []
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg: clash_proxies.append(node_cfg)

    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        # 第一行必须是这个，才能在 Clash 里刷出流量信息
        f.write(f"# subscription-userinfo: upload=0; download=0; total=1073741824000000; expire=4070880000\n")
        f.write(f'# profile-title: "{MY_SIGNATURE}"\n')
        f.write(f"# {SLOGAN_1}\n")
        f.write(f"# {SLOGAN_2}\n\n")
        
        config = {
            "port": 7890, "socks-port": 7891, "allow-lan": True, "mode": "rule", "log-level": "info",
            "proxies": clash_proxies,
            "proxy-groups": [
                {"name": "🔰 节点选择", "type": "select", "proxies": ["🎯 全球直连"] + [p['name'] for p in clash_proxies]},
                {"name": "🎯 全球直连", "type": "select", "proxies": ["DIRECT", "🔰 节点选择"]}
            ],
            "rules": ["MATCH,🔰 节点选择"]
        }
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"✨ 导出成功！节点数: {len(clash_proxies)}")

if __name__ == "__main__":
    main()
