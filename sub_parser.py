import os, requests, base64, re, socket, maxminddb, concurrent.futures, json, yaml, hashlib, time, functools
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

def parse_uri_to_clash(uri):
    if isinstance(uri, dict): return uri
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

def fetch_source(url):
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=3)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        if "proxies:" in content or ("port:" in content and "mode:" in content):
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict) and 'proxies' in data: return data['proxies']
            except: pass
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except: return []

def process_node_full(item, reader):
    """处理地理识别并尝试保留/还原 URI 用于 txt 导出"""
    node = parse_uri_to_clash(item)
    if not node: return None
    
    server = node.get('server')
    nid = f"{server}:{node.get('port')}:{node.get('type')}"
    ip = get_ip(server)
    
    c_name, flag = "未知地区", "🌐"
    if ip and reader:
        match = reader.get(ip)
        if match:
            names = match.get('country', {}).get('names', {})
            c_name = names.get('zh-CN', "未知地区")
            flag = get_flag(match.get('country', {}).get('iso_code'))
            
    sid = get_short_id(nid)
    new_name = f"{flag} {c_name} 打倒美帝国主义及其一切走狗_{sid}"
    
    # 克隆节点字典并更新名称
    clash_node = node.copy()
    clash_node['name'] = new_name
    
    # 尝试构造原始 URI（如果输入本身是字符串则直接用，否则由字典标记）
    raw_uri = item if isinstance(item, str) else f"#DictNode:{new_name}"
    
    return nid, clash_node, raw_uri

def main():
    link_env = os.environ.get('LINK', '').strip()
    if not link_env: return
    
    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    raw_items = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results: raw_items.extend(r)
    
    mmdb_path = 'GeoLite2-Country.mmdb'
    reader = maxminddb.open_database(mmdb_path) if os.path.exists(mmdb_path) else None
    
    final_proxies = []
    final_uris = []
    seen_nodes = set()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(process_node_full, item, reader) for item in raw_items]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                nid, clash_node, raw_uri = res
                if nid not in seen_nodes:
                    seen_nodes.add(nid)
                    final_proxies.append(clash_node)
                    # 仅保留有效的协议链接用于 txt 导出
                    if "://" in raw_uri:
                        # 替换 URI 中的标签为新名称
                        base_part = raw_uri.split('#')[0]
                        final_uris.append(f"{base_part}#{clash_node['name']}")
                    
    if reader: reader.close()
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    node_count = len(final_proxies)
    os.makedirs('data', exist_ok=True)
    
    # 1. 导出 clash.yaml
    full_config = CLASH_BASE_CONFIG.copy()
    p_names = [p['name'] for p in final_proxies]
    full_config.update({
        "proxies": final_proxies,
        "proxy-groups": [
            {"name": "🔰 节点选择", "type": "select", "proxies": ["🚀 自动测速", "DIRECT"] + p_names},
            {"name": "🚀 自动测速", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": p_names}
        ],
        "rules": ["MATCH,🔰 节点选择"]
    })
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write(f'# 美帝国主义是纸老虎\n# Last Updated: {update_time}\n# Total Nodes: {node_count}\n\n')
        yaml.safe_dump(full_config, f, allow_unicode=True, sort_keys=False, indent=2)

    # 2. 导出 nodes.txt
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write(f"# 美帝国主义是纸老虎\n# Updated: {update_time}\n# Total: {len(final_uris)}\n")
        f.write("\n".join(final_uris) + "\n")

    # 3. 导出 v2ray.txt (Base64)
    nodes_content = "\n".join(final_uris) + "\n"
    b64_content = base64.b64encode(nodes_content.encode('utf-8')).decode('utf-8')
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(b64_content)
        
    print(f"✨ 任务完成！Clash节点: {node_count}, URI节点: {len(final_uris)}")

if __name__ == "__main__":
    main()
