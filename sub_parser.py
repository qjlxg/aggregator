import os, requests, base64, re, socket, maxminddb, concurrent.futures, json, yaml, hashlib
from urllib.parse import urlparse, unquote

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

def get_short_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:4]

def parse_uri_to_clash(uri):
    """支持主流协议解析为 Clash 字典格式"""
    try:
        if "://" not in uri: return None
        parts = uri.split('#')
        base_uri, tag = parts[0], unquote(parts[1]) if len(parts) > 1 else "Node"
        parsed = urlparse(base_uri)
        if not parsed.hostname: return None
        node = {"name": tag, "server": parsed.hostname, "port": int(parsed.port or 443), "udp": True}
        query = {k.lower(): unquote(v) for k, v in [p.split('=', 1) for p in parsed.query.split('&') if '=' in p]} if parsed.query else {}

        if parsed.scheme == 'ss':
            auth = decode_base64(parsed.netloc.split('@')[0])
            if ':' in auth:
                node.update({"type": "ss", "cipher": auth.split(':')[0], "password": auth.split(':')[1]})
                return node
        elif parsed.scheme == 'vmess':
            v2 = json.loads(decode_base64(base_uri.replace("vmess://", "")))
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

def rename_node(uri, reader):
    """根据 IP 定位重命名节点"""
    try:
        if "#" not in uri: return uri
        base_uri, original_tag = uri.split('#', 1)
        original_tag = unquote(original_tag).strip()
        
      
        if any(x in original_tag for x in ["流量", "到期", "重置"]): return None

        parsed = urlparse(base_uri)
        ip = get_ip(parsed.hostname)
        country_name, flag = "未知地区", "🌐"
        
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))

        # 格式：国旗 国家名 唯一ID
        return f"{base_uri}#{flag} {country_name} {get_short_id(base_uri)}"
    except:
        return uri

def fetch_source(url_info):
    idx, url = url_info
    try:
        resp = requests.get(url, headers={'User-Agent': 'ClashMeta'}, timeout=15)
        content = resp.text if "://" in resp.text else decode_base64(resp.text)
        nodes = re.findall(r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+', content, re.IGNORECASE)
        return nodes
    except:
        return []

def main():
    link_env = os.environ.get('LINK', '').strip()
    if not link_env:
        print("❌ 未找到LINK。")
        return

   
    for line in link_env.split('\n'):
        if line.strip(): print(f"::add-mask::{line.strip()}")

    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    all_uris = []
    
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, list(enumerate(links))))
        for r in results: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    
    final_uris = []
    for u in unique_uris:
        renamed = rename_node(u, reader)
        if renamed: final_uris.append(renamed)
    if reader: reader.close()

    clash_proxies = [parse_uri_to_clash(u) for u in final_uris if parse_uri_to_clash(u)]
    if not clash_proxies:
        print("⚠️ 未抓取到有效节点。")
        return

  
    os.makedirs('data', exist_ok=True)

    # 1. 保存 data/clash.yaml
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write('# profile-title: "Subscription Generated By Gemini"\n')
        proxy_names = [p['name'] for p in clash_proxies]
        config = {
            "proxies": clash_proxies,
            "proxy-groups": [
                {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + proxy_names},
                {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": proxy_names}
            ],
            "rules": ["MATCH,🔰 节点选择"]
        }
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    # 2. 保存 data/nodes.txt (明文列表)
    nodes_content = "\n".join(final_uris) + "\n"
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write(nodes_content)

    # 3. 保存 data/v2ray.txt (Base64 编码)
    b64_content = base64.b64encode(nodes_content.encode('utf-8')).decode('utf-8')
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"✨ 任务完成！共计抓取并处理节点: {len(clash_proxies)}")
    print(f"📂 文件已保存至 data 目录: clash.yaml, nodes.txt, v2ray.txt")

if __name__ == "__main__":
    main()
