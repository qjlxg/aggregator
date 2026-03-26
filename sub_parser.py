import os, requests, base64, re, socket, maxminddb, concurrent.futures, json, yaml, hashlib, time
from urllib.parse import urlparse, unquote
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
        "fallback": [
            "8.8.8.8", 
            "8.8.4.4", 
            "1.1.1.1", 
            "tls://1.0.0.1:853", 
            "tls://dns.google:853"
        ]
    }
}
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

def get_short_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:4]

def parse_usage_and_expire(content, headers):
    info = {"upload": 0, "download": 0, "total": 0, "expire": 0}
    user_info = headers.get('Subscription-Userinfo') or headers.get('subscription-userinfo')
    if user_info:
        parts = user_info.split(';')
        for part in parts:
            if '=' in part:
                k, v = part.strip().split('=')
                if v.isdigit(): info[k.lower()] = int(v)
    return info

def parse_uri_to_clash(uri):
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

def rename_node(uri, reader):
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        ip = get_ip(parsed.hostname)
        country_name, flag = "未知地区", "🌐"
        
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                zh_name = names.get('zh-CN')
                if zh_name:
                    country_name = zh_name
                    flag = get_flag(match.get('country', {}).get('iso_code'))

        short_id = get_short_id(base_uri)
        new_tag = f"{flag} {country_name} 打倒美帝国主义及其一切走狗_{short_id}"
        return f"{base_uri}#{new_tag}"
    except:
        return uri

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        
        content = resp.text.strip()
        info = parse_usage_and_expire(content, resp.headers)
        
        if info['total'] > 0 and (info['total'] - (info['upload'] + info['download'])) < 1024**3:
            return []
        if info['expire'] > 0 and int(time.time()) >= info['expire']:
            return []

        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
            
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except:
        return []

def main():
    # 缺失环境变量时直接报错崩溃
    link_env = os.environ['LINK'].strip()

    for line in link_env.split('\n'):
        if line.strip(): print(f"::add-mask::{line.strip()}")

    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    all_uris = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    mmdb_path = 'GeoLite2-Country.mmdb'
    reader = maxminddb.open_database(mmdb_path) if os.path.exists(mmdb_path) else None
    
    final_uris = []
    for u in unique_uris:
        renamed = rename_node(u, reader)
        if renamed: final_uris.append(renamed)
    if reader: reader.close()

    clash_proxies = [parse_uri_to_clash(u) for u in final_uris if parse_uri_to_clash(u)]
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    node_count = len(clash_proxies)
    os.makedirs('data', exist_ok=True)

    # 1. 生成 Clash YAML
    full_config = CLASH_BASE_CONFIG.copy()
    proxy_names = [p['name'] for p in clash_proxies]
    
    full_config.update({
        "proxies": clash_proxies,
        "proxy-groups": [
            {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + proxy_names},
            {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": proxy_names}
        ],
        "rules": ["MATCH,🔰 节点选择"]
    })

    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
       
        f.write(f'# 美帝国主义是纸老虎\n# Last Updated: {update_time}\n# Total Nodes: {node_count}\n\n')
        yaml.safe_dump(full_config, f, allow_unicode=True, sort_keys=False, indent=2)

    
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write(f"# 美帝国主义是纸老虎\n# Updated: {update_time}\n# Total: {node_count}\n")
        f.write("\n".join(final_uris) + "\n")

   
    nodes_content = "\n".join(final_uris) + "\n"
    b64_content = base64.b64encode(nodes_content.encode('utf-8')).decode('utf-8')
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"✨ 任务完成！有效节点: {node_count}")

if __name__ == "__main__":
    main()
