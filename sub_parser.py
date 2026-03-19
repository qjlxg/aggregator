import os, requests, base64, re, socket, maxminddb, concurrent.futures
from urllib.parse import urlparse

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

def rename_node(uri, reader):
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        protocol = parsed.scheme.upper()
        
        hostname = parsed.hostname
        ip = get_ip(hostname)
        country_name = "未知"
        flag = "🏳"
        
        if ip and reader:
            match = reader.get(ip)
            if match:
                # 尝试获取中文名，不存在则取英文名
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        
        new_name = f"{flag} {country_name} | {protocol}"
        return f"{base_uri}#{new_name}"
    except:
        return uri

def fetch_source(url):
    try:
        headers = {'User-Agent': 'v2rayN/6.23'}
   
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except:
        return []

def main():
  
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    
    if not links:
        print("⚠️ 未发现待处理的数据源。")
        return

    all_uris = []
  
    print(f"🔄 正在处理 {len(links)} 个数据源...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        reader = maxminddb.open_database('GeoLite2-Country.mmdb')
    
    final_nodes = []
    for uri in unique_uris:
        final_nodes.append(rename_node(uri, reader))
    
    if reader: reader.close()

    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes))
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(base64.b64encode('\n'.join(final_nodes).encode('utf-8')).decode('utf-8'))

    print(f"✨ 处理完成。共提取有效节点: {len(unique_uris)}")

if __name__ == "__main__":
    main()
