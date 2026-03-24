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
        data = data.replace("-", "+").replace("_", "/") # 处理 URL Safe Base64
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

def get_ip(hostname):
    try: return socket.gethostbyname(hostname)
    except: return None

def parse_uri_to_clash(uri):
    """最强解析引擎：处理特殊字符，防止 YAML 报错"""
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
            v2_json = json.loads(decode_base64(base_uri.replace("vmess://", "")))
            node.update({"type": "vmess", "uuid": v2_json.get('id'), "alterId": int(v2_json.get('aid', 0)), "cipher": "auto", "tls": v2_json.get('tls') in ["tls", True], "network": v2_json.get('net', 'tcp')})
            if node["network"] == 'ws': node["ws-opts"] = {"path": v2_json.get('path', '/'), "headers": {"Host": v2_json.get('host', '')}}
            return node
        elif scheme == 'vless':
            node.update({"type": "vless", "uuid": parsed.username, "tls": query.get('security') in ['tls', 'reality'], "servername": query.get('sni'), "network": query.get('type', 'tcp')})
            if query.get('security') == 'reality':
                node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
            return node
        elif scheme in ['hysteria2', 'hy2']:
            node.update({"type": "hysteria2", "password": parsed.username or query.get('auth'), "sni": query.get('sni'), "skip-cert-verify": True})
            return node
        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": query.get('sni'), "skip-cert-verify": True})
            return node
    except: return None
    return None

def rename_node(uri, reader):
    try:
        if "#" not in uri: return uri
        base_uri, original_tag = uri.split('#', 1)
        original_tag = unquote(original_tag)
        
        # 过滤掉原本源里的“伪装信息节点”，避免名字太乱
        if any(x in original_tag for x in ["剩余流量", "过期时间", "重置", "GB"]):
            return uri

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
        headers = {'User-Agent': 'ClashMeta/1.16.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
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

    # 1. 生成 nodes.txt
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))

    # 2. 生成完全兼容的 clash.yaml
    clash_proxies = []
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg: clash_proxies.append(node_cfg)

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
        # 使用 safe_dump 并禁止排序，保证生成的 YAML 最稳定
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"✨ 成功！有效节点: {len(clash_proxies)}")

if __name__ == "__main__":
    main()
