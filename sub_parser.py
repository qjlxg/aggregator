import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml
from urllib.parse import urlparse, unquote

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
    """简单解析 URI 为 Clash 字典格式"""
    try:
        parts = uri.split('#')
        tag = unquote(parts[1]) if len(parts) > 1 else "Unnamed"
        base_uri = parts[0]
        parsed = urlparse(base_uri)
        scheme = parsed.scheme.lower()
        
        node = {"name": tag, "server": parsed.hostname, "port": parsed.port, "udp": True}
        
        if scheme == 'ss':
            # 处理 ss://method:password@host:port
            userinfo = decode_base64(parsed.username + '==' if parsed.username else "").split(':')
            if len(userinfo) == 2:
                node.update({"type": "ss", "cipher": userinfo[0], "password": userinfo[1]})
            else:
                # 处理 ss://base64(method:password)@host:port
                info = decode_base64(parsed.netloc.split('@')[0]).split(':')
                node.update({"type": "ss", "cipher": info[0], "password": info[1]})
        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": parsed.hostname, "skip-cert-verify": True})
        elif scheme == 'vmess':
            # vmess 比较复杂，通常是 base64 后的 json
            v2_data = json.loads(decode_base64(base_uri.replace("vmess://", "")))
            node.update({
                "type": "vmess", "uuid": v2_data.get('id'), "alterId": int(v2_data.get('aid', 0)),
                "cipher": "auto", "tls": v2_data.get('tls') == "tls", "network": v2_data.get('net', 'tcp')
            })
            if v2_data.get('net') == 'ws':
                node["ws-opts"] = {"path": v2_data.get('path', '/'), "headers": {"Host": v2_data.get('host', '')}}
        else:
            return None # 暂不支持的格式
        return node
    except:
        return None

def parse_usage_and_expire(text, headers):
    info = {}
    header = headers.get('Subscription-Userinfo') or headers.get('subscription-userinfo')
    if header:
        for item in header.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                try: info[k.strip().lower()] = int(v.strip())
                except: pass
        if info: return info
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for k in ["upload", "download", "total", "expire", "expiration"]:
                if k in data:
                    try: info[k] = int(data[k])
                    except: pass
            if info: return info
    except: pass
    for item in text.replace("\n", ";").split(";"):
        if "=" in item:
            parts = item.split("=", 1)
            if len(parts) == 2:
                k, v = parts
                try: info[k.strip().lower()] = int(v.strip())
                except: pass
    return info

def rename_node(uri, reader):
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        protocol = parsed.scheme.upper()
        hostname = parsed.hostname
        ip = get_ip(hostname)
        country_name, flag = "未知", "🏳"
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        return f"{base_uri}#{flag} {country_name} | {protocol}"
    except: return uri

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        info = parse_usage_and_expire(content, resp.headers)
        u, d, total = info.get("upload", 0), info.get("download", 0), info.get("total", 0)
        expire = info.get("expire") or info.get("expiration")
        THRESHOLD_1GB = 1024 * 1024 * 1024
        if total > 0 and (total - (u + d)) < THRESHOLD_1GB: return []
        if expire and expire > 0 and int(time.time()) >= expire: return []
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except: return []

def main():
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links: return print("❌ 未检测到 LINK 环境变量。")

    print(f"🔄 正在处理 {len(links)} 个源...")
    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    
    final_nodes_uris = [rename_node(uri, reader) for uri in unique_uris]
    if reader: reader.close()

    # 1. 保存原始 txt 格式
    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(base64.b64encode('\n'.join(final_nodes_uris).encode('utf-8')).decode('utf-8'))

    # 2. 生成 Clash YAML
    clash_proxies = []
    proxy_names = []
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg:
            clash_proxies.append(node_cfg)
            proxy_names.append(node_cfg['name'])

    clash_config = {
        "port": 7890, "socks-port": 7891, "allow-lan": True, "mode": "Rule", "log-level": "info",
        "external-controller": ":9090",
        "proxies": clash_proxies,
        "proxy-groups": [
            {"name": "🔰 节点选择", "type": "select", "proxies": ["🎯 全球直连"] + proxy_names},
            {"name": "🎯 全球直连", "type": "select", "proxies": ["DIRECT", "🔰 节点选择"]}
        ],
        "rules": ["MATCH,🔰 节点选择"]
    }

    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False)

    print(f"✨ 任务完成！有效节点: {len(unique_uris)}，已保存为 nodes.txt, v2ray.txt 和 clash.yaml")

if __name__ == "__main__":
    main()
