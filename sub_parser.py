import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml, hashlib
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

def get_short_id(text):
    """生成4位唯一哈希，防止重名导致Clash报错"""
    return hashlib.md5(text.encode()).hexdigest()[:4]

def parse_uri_to_clash(uri):
    """最强全协议解析引擎"""
    try:
        if "://" not in uri: return None
        parts = uri.split('#')
        base_uri = parts[0]
        raw_tag = unquote(parts[1]) if len(parts) > 1 else "Node"
        tag = re.sub(r'[\"\'\[\]\{\}\>\<\#]', '', raw_tag).strip()
        
        parsed = urlparse(base_uri)
        scheme = parsed.scheme.lower()
        if not parsed.hostname: return None
        
        node = {"name": tag, "server": parsed.hostname, "port": int(parsed.port or 443), "udp": True}
        query = {k.lower(): unquote(v) for k, v in [p.split('=', 1) for p in parsed.query.split('&') if '=' in p]} if parsed.query else {}

        if scheme == 'ss':
            if '@' in parsed.netloc:
                auth_decoded = decode_base64(parsed.netloc.split('@')[0])
                if ':' in auth_decoded:
                    method, password = auth_decoded.split(':', 1)
                    node.update({"type": "ss", "cipher": method, "password": password})
                    return node
            return None
        elif scheme == 'vmess':
            try:
                v2 = json.loads(decode_base64(base_uri.replace("vmess://", "")))
                node.update({"type": "vmess", "uuid": v2.get('id'), "alterId": int(v2.get('aid', 0)), "cipher": "auto", "tls": v2.get('tls') in ["tls", True], "network": v2.get('net', 'tcp')})
                if node["network"] == 'ws': node["ws-opts"] = {"path": v2.get('path', '/'), "headers": {"Host": v2.get('host', '')}}
                elif node["network"] == 'grpc': node["grpc-opts"] = {"grpc-service-name": v2.get('path', '')}
                return node
            except: return None
        elif scheme == 'vless':
            node.update({"type": "vless", "uuid": parsed.username, "tls": query.get('security') in ['tls', 'reality'], "servername": query.get('sni'), "network": query.get('type', 'tcp')})
            if query.get('security') == 'reality': node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
            if query.get('flow'): node["flow"] = query.get('flow')
            if query.get('type') == 'grpc': node["grpc-opts"] = {"grpc-service-name": query.get('serviceName', '')}
            return node
        elif scheme in ['hysteria2', 'hy2']:
            node.update({"type": "hysteria2", "password": parsed.username or query.get('auth'), "sni": query.get('sni'), "skip-cert-verify": True})
            return node
        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": query.get('sni'), "skip-cert-verify": True})
            return node
        elif scheme == 'tuic':
            node.update({"type": "tuic", "uuid": parsed.username, "password": parsed.password, "sni": query.get('sni'), "alpn": [query.get('alpn', 'h3')], "skip-cert-verify": True})
            return node
        elif scheme == 'socks':
            node.update({"type": "socks5", "username": parsed.username, "password": parsed.password})
            return node
    except: return None
    return None

def rename_node(uri, reader):
    """保底命名逻辑：确保所有节点格式高度统一"""
    try:
        if "#" not in uri: return uri
        base_uri, original_tag = uri.split('#', 1)
        original_tag = unquote(original_tag).strip()
        
        # 过滤广告
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
        
        # 统一名称对齐逻辑
        final_flag = flag if flag else "🌐"
        # 如果没识别到国家，用原始备注名；如果备注名太乱，保底显示 Unknown
        final_country = country_name if country_name else (original_tag if len(original_tag) < 15 else "未知节点")
        
        return f"{base_uri}#{final_flag} {final_country} {get_short_id(base_uri)} {MY_REMARK}"
    except:
        return uri

def fetch_source(url_info):
    idx, url = url_info
    domain_peek = urlparse(url).netloc[:10] + "..."
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
    
    # 全局屏蔽网址日志
    for line in link_env.split('\n'):
        if line.strip(): print(f"::add-mask::{line.strip()}")

    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, list(enumerate(links))))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        final_nodes_uris = list(executor.map(lambda u: rename_node(u, reader), unique_uris))
    if reader: reader.close()

    clash_proxies = []
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg: clash_proxies.append(node_cfg)

    if not clash_proxies:
        print("❌ 错误：未发现有效节点，请检查订阅源。")
        return

    os.makedirs('data', exist_ok=True)
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write(f"# subscription-userinfo: upload=0; download=0; total=1073741824000000; expire=4070880000\n")
        f.write(f'# profile-title: "{MY_SIGNATURE}"\n')
        f.write(f"# {SLOGAN_1} | {SLOGAN_2}\n\n")
        
        proxy_names = [p['name'] for p in clash_proxies]
        config = {
            "port": 7890, "socks-port": 7891, "allow-lan": True, "mode": "rule",
            "proxies": clash_proxies,
            "proxy-groups": [
                {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + proxy_names},
                {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": proxy_names}
            ],
            "rules": ["MATCH,🔰 节点选择"]
        }
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"✨ 任务完成！共计有效节点: {len(clash_proxies)}")

if __name__ == "__main__":
    main()
