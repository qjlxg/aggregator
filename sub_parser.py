import os, requests, base64, re, socket, maxminddb, concurrent.futures
from urllib.parse import urlparse

# 国旗 Emoji 映射表 (ISO 国家代码 -> Emoji)
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
    """解析域名为 IP"""
    try: return socket.gethostbyname(hostname)
    except: return None

def rename_node(uri, reader):
    """解析 URI 并在 fragment 中添加 [国家|协议]"""
    try:
        # 移除原有的备注(fragment)
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        protocol = parsed.scheme.upper()
        
        # 提取主机名并查询国家
        hostname = parsed.hostname
        ip = get_ip(hostname)
        country_name = "未知"
        flag = "🏳"
        
        if ip and reader:
            match = reader.get(ip)
            if match:
                country_name = match.get('country', {}).get('names', {}).get('zh-CN', match['country']['names']['en'])
                flag = get_flag(match.get('country', {}).get('iso_code'))
        
        # 重新拼接：协议://内容#国旗 国家|协议
        new_name = f"{flag} {country_name} | {protocol}"
        return f"{base_uri}#{new_name}"
    except:
        return uri

def fetch_source(url):
    """单个源的抓取逻辑"""
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
    
    # 1. 多线程并发抓取
    all_uris = []
    print(f"🚀 开始并发抓取 {len(links)} 个订阅源...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    print(f"✅ 抓取完成，共 {len(unique_uris)} 个原始节点。开始解析地理位置...")

    # 2. 地理位置重命名
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        reader = maxminddb.open_database('GeoLite2-Country.mmdb')
    
    final_nodes = []
    # 这里也可以用多线程加速 DNS 解析，但为了稳定采用顺序处理
    for uri in unique_uris:
        final_nodes.append(rename_node(uri, reader))
    
    if reader: reader.close()

    # 3. 存储
    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes))
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(base64.b64encode('\n'.join(final_nodes).encode('utf-8')).decode('utf-8'))

    print(f"🎉 全部处理完成！结果已存入 data 目录。")

if __name__ == "__main__":
    main()
