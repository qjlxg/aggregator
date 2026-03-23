import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json
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

def parse_usage_and_expire(text, headers):
    """解析流量和到期时间"""
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
    """抓取源并进行流量/时间校验"""
    try:
        # 设置 User-Agent 为主流客户端，诱导服务器返回 Subscription-Userinfo
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        
     
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        
        content = resp.text.strip()
        
        # --- 流量与到期判定 ---
        info = parse_usage_and_expire(content, resp.headers)
        u = info.get("upload", 0)
        d = info.get("download", 0)
        total = info.get("total", 0)
        expire = info.get("expire") or info.get("expiration")
        now = int(time.time())

        # 阈值：1GB (单位：Byte)
        THRESHOLD_1GB = 1024 * 1024 * 1024

        # 1. 判定流量：如果有总量限制，且剩余流量不足 1GB，直接排除
        if total > 0:
            remaining = total - (u + d)
            if remaining < THRESHOLD_1GB:
                # 流量不足 1GB 或已透支，返回空列表
                return []

        # 2. 判定过期：如果设置了过期时间(且不为0)，且当前时间已超过过期时间，排除
        if expire and expire > 0:
            if now >= expire:
                return []

        # --- 提取节点 ---
        # 自动识别 Base64 或 纯文本 URI
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
        print("❌ 未检测到 LINK 环境变量。")
        return

    print(f"🔄 正在处理 {len(links)} 个源，排除剩余流量 < 1GB 或已过期的订阅...")
    
    all_uris = []
    # 使用 20 线程并发请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    # 去重
    unique_uris = list(set(all_uris))
    
    # 加载 GeoLite 数据库进行节点命名
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        reader = maxminddb.open_database('GeoLite2-Country.mmdb')
    
    final_nodes = []
    for uri in unique_uris:
        final_nodes.append(rename_node(uri, reader))
    
    if reader: reader.close()

    # 存储到 data 目录
    os.makedirs('data', exist_ok=True)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes))
    
    # 导出 Base64 格式
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64_content = base64.b64encode('\n'.join(final_nodes).encode('utf-8')).decode('utf-8')
        f.write(b64_content)

    print(f"✨ 任务完成！")
    print(f"📊 原始节点总数: {len(all_uris)}")
    print(f"💎 过滤/去重后有效节点: {len(unique_uris)}")

if __name__ == "__main__":
    main()
