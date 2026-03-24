import os, requests, base64, re, socket, maxminddb, concurrent.futures, time, json, yaml
from urllib.parse import urlparse, unquote
from datetime import datetime

# ================= 配置区 =================
MY_SIGNATURE = "🔋 搬砖专用通道 (非战斗人员请撤离)"
MY_REMARK = "| 别乱点"
SLOGAN_1 = "# 节点虽多，请且用且珍惜"
SLOGAN_2 = "# 正在连接到月球背面..."


NODES_RAW_URL = "https://raw.githubusercontent.com/qjlxg/aggregator/refs/heads/main/data/nodes.txt"
# ==========================================

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
        ip = get_ip(parsed.hostname)
        country_name, flag = "Unknown", "🌐"
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))
        return f"{base_uri}#{flag} {country_name} {MY_REMARK}"
    except: return uri

def fetch_source(url):
   
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        content = resp.text.strip()
        
        info = {}
        h = resp.headers.get('Subscription-Userinfo', '')
        for item in h.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                try: info[k.strip().lower()] = int(v.strip())
                except: pass
        if info.get("total", 0) > 0:
            if (info["total"] - (info.get("upload", 0) + info.get("download", 0))) < (1024**3): return []
        if info.get("expire") and info["expire"] > 0 and int(time.time()) >= info["expire"]: return []

        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except: return []

def main():
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links: return print("❌ 未检测到 LINK 环境变量")

    print(f"🔄 正在并发抓取 {len(links)} 个源...")
    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = maxminddb.open_database('GeoLite2-Country.mmdb') if os.path.exists('GeoLite2-Country.mmdb') else None
    
    print(f"🏷️ 正在解析 {len(unique_uris)} 个节点...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        final_nodes_uris = list(executor.map(lambda u: rename_node(u, reader), unique_uris))
    if reader: reader.close()

    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs('data', exist_ok=True)

    # 1. 保存 nodes.txt (用于 Proxy Provider 远程加载)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes_uris))

    # 2. 保存 v2ray.txt (Base64 格式，用于小火箭等)
    v2ray_content = '\n'.join(final_nodes_uris)
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(base64.b64encode(v2ray_content.encode('utf-8')).decode('utf-8'))

    # 3. 生成专业级 Clash YAML (带订阅面板)
    print(f"🛠️ 正在生成专业版 Clash 配置文件...")
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        # 写入头部信息
        f.write(f"# -------------------------------------------------------------------\n")
        f.write(f"# 订阅信息及标题\n")
        f.write(f"# 标题: {MY_SIGNATURE}\n")
        f.write(f"# 流量: 999,999 GB (约 976.5 TB)\n")
        f.write(f"# 到期: 2099-12-31\n")
        f.write(f"# -------------------------------------------------------------------\n")
        f.write(f"# subscription-userinfo: upload=0; download=0; total=1073740742656000; expire=4070880000\n")
        f.write(f'# profile-title: "{MY_SIGNATURE}"\n')
        f.write(f"{SLOGAN_1}\n")
        f.write(f"{SLOGAN_2}\n\n")

        # 核心配置字典
        clash_dict = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": True,
            "mode": "Rule",
            "log-level": "info",
            "ipv6": False,
            "external-controller": ":9090",
            "dns": {
                "enable": True,
                "ipv6": False,
                "enhanced-mode": "fake-ip",
                "fake-ip-range": "198.18.0.1/16",
                "nameserver": ["119.29.29.29", "223.5.5.5"],
                "fallback": ["8.8.8.8", "8.8.4.4", "tls://1.0.0.1:853", "tls://dns.google:853"]
            },
            "proxy-providers": {
                "free-nodes": {
                    "type": "http",
                    "url": NODES_RAW_URL,
                    "interval": 3600,
                    "path": "./proxies/free.yaml",
                    "health-check": {"enable": True, "interval": 600, "url": "http://www.gstatic.com/generate_204"}
                }
            },
            "proxy-groups": [
                {
                    "name": "🚀 节点选择",
                    "type": "select",
                    "proxies": ["⚡ 自动测速", "DIRECT"],
                    "use": ["free-nodes"]
                },
                {
                    "name": "⚡ 自动测速",
                    "type": "url-test",
                    "url": "http://www.gstatic.com/generate_204",
                    "interval": 300,
                    "use": ["free-nodes"]
                }
            ],
            "rules": [
                "GEOIP,LAN,DIRECT",
                "GEOIP,CN,DIRECT",
                "MATCH,🚀 节点选择"
            ]
        }
        yaml.dump(clash_dict, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"✨ 任务完成！有效节点: {len(final_nodes_uris)} | 更新时间: {update_time}")

if __name__ == "__main__":
    main()
