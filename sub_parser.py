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
    """DNS 解析获取 IP"""
    try: return socket.gethostbyname(hostname)
    except: return None

def parse_uri_to_clash(uri):
    """深度解析各种协议 URI 并转换为 Clash 字典格式"""
    try:
        parts = uri.split('#')
        tag = unquote(parts[1]) if len(parts) > 1 else "Unnamed"
        base_uri = parts[0]
        parsed = urlparse(base_uri)
        scheme = parsed.scheme.lower()
        
        # 基础公共字段
        node = {"name": tag, "server": parsed.hostname, "port": parsed.port or 443, "udp": True}
        
        # 获取查询参数
        query = dict([pair.split('=', 1) for pair in parsed.query.split('&')] if parsed.query else [])

        if scheme == 'ss':
            auth = (parsed.username + '==' if parsed.username else "")
            userinfo = decode_base64(auth).split(':')
            if len(userinfo) == 2:
                node.update({"type": "ss", "cipher": userinfo[0], "password": userinfo[1]})
            else:
                info = decode_base64(parsed.netloc.split('@')[0]).split(':')
                node.update({"type": "ss", "cipher": info[0], "password": info[1]})

        elif scheme == 'vmess':
            v2_data = json.loads(decode_base64(base_uri.replace("vmess://", "")))
            node.update({
                "type": "vmess", "uuid": v2_data.get('id'), "alterId": int(v2_data.get('aid', 0)),
                "cipher": "auto", "tls": v2_data.get('tls') == "tls", "network": v2_data.get('net', 'tcp')
            })
            if v2_data.get('net') == 'ws':
                node["ws-opts"] = {"path": v2_data.get('path', '/'), "headers": {"Host": v2_data.get('host', '')}}
            elif v2_data.get('net') == 'grpc':
                node["grpc-opts"] = {"grpc-service-name": v2_data.get('path', '')}

        elif scheme == 'vless':
            node.update({
                "type": "vless", "uuid": parsed.username,
                "tls": query.get('security') in ['tls', 'reality'],
                "servername": query.get('sni'),
                "network": query.get('type', 'tcp')
            })
            if query.get('flow'): node["flow"] = query.get('flow')
            if query.get('security') == 'reality':
                node["reality-opts"] = {"public-key": query.get('pbk'), "short-id": query.get('sid', '')}
                node["client-fingerprint"] = query.get('fp', 'chrome')
            if node["network"] == 'ws':
                node["ws-opts"] = {"path": query.get('path', '/'), "headers": {"Host": query.get('host', '')}}
            elif node["network"] == 'grpc':
                node["grpc-opts"] = {"grpc-service-name": query.get('serviceName', '')}

        elif scheme in ['hysteria2', 'hy2']:
            node.update({
                "type": "hysteria2", "password": parsed.username,
                "sni": query.get('sni'), "skip-cert-verify": True
            })
            if query.get('obfs') == 'password':
                node["obfs"] = "password"
                node["obfs-password"] = query.get('obfs-password')

        elif scheme == 'trojan':
            node.update({
                "type": "trojan", "password": parsed.username,
                "sni": query.get('sni') or parsed.hostname,
                "skip-cert-verify": True
            })
        
        else:
            return None
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
    return info

def rename_node(uri, reader):
    """并行调用的重命名逻辑"""
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        protocol = parsed.scheme.upper()
        ip = get_ip(parsed.hostname)
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
        
        # 流量校验 (1GB)
        if info.get("total", 0) > 0:
            remaining = info["total"] - (info.get("upload", 0) + info.get("download", 0))
            if remaining < (1024 * 1024 * 1024): return []
            
        # 过期校验
        expire = info.get("expire") or info.get("expiration")
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
    if not links:
        print("❌ 未检测到 LINK 环境变量。")
        return

    print(f"🔄 正在并发抓取 {len(links)} 个源...")
    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    
    # 加载 GeoDB
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        reader = maxminddb.open_database('GeoLite2-Country.mmdb')

    # 并行解析 DNS 和地理位置
    print(f"🏷️ 正在并行解析 {len(unique_uris)} 个节点的地理位置...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        final_nodes_uris = list(executor.map(lambda u: rename_node(u, reader), unique_uris))
    
    if reader: reader.close()

    # 存储基础文件
    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64_content = base64.b64encode('\n'.join(final_nodes_uris).encode('utf-8')).decode('utf-8')
        f.write(b64_content)

    # 生成 Clash YAML
    print(f"🛠️ 正在生成 Clash 配置文件...")
    clash_proxies = []
    proxy_names = []
    for uri in final_nodes_uris:
        node_cfg = parse_uri_to_clash(uri)
        if node_cfg:
            clash_proxies.append(node_cfg)
            proxy_names.append(node_cfg['name'])

    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
        # 写入更新时间注释
        f.write(f"# Generated at: {update_time}\n")
        # 写入 YAML 配置
        yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"✨ 任务完成！有效节点: {len(clash_proxies)} | 更新时间: {update_time}")

if __name__ == "__main__":
    main()
