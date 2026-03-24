import os
import requests
import base64
import re
import socket
import maxminddb
import concurrent.futures
import time
import json
import random
from urllib.parse import urlparse, unquote, quote

# --- 全局配置与缓存 ---
dns_cache = {}
UA_LIST = [
    "ClashMeta/1.16.0 v2rayN/6.23",
    "ClashForWindows/0.20.39",
    "Stash/2.4.5 iPhone15,2 iOS/17.4.1",
    "Shadowrocket/2.2.38",
    "Surfboard/2.19.2"
]

def mask_url(url):
    """隐私保护：日志中仅显示链接前 3 位"""
    if not url: return "Unknown"
    return f"{url[:3]}***"

def get_flag(code):
    """ISO 国家代码转 Emoji 国旗"""
    if not code or len(code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def decode_base64(data):
    """Base64 解码支持"""
    if not data: return ""
    try:
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

def get_ip(hostname):
    """带缓存的 DNS 解析"""
    if not hostname: return None
    if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', hostname): return hostname
    if hostname in dns_cache: return dns_cache[hostname]
    try:
        ip = socket.gethostbyname(hostname)
        dns_cache[hostname] = ip
        return ip
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
                if k in data: info[k] = int(data[k])
    except: pass
    return info

def rename_node(uri, reader):
   
    try:
        base_uri = uri.split('#')[0] if '#' in uri else uri
        parsed = urlparse(base_uri)
        protocol = parsed.scheme.upper()
        if protocol == "HYSTERIA2": protocol = "HY2"
        
        hostname = parsed.hostname
        if not hostname and "@" in parsed.netloc:
            hostname = parsed.netloc.split("@")[-1].split(":")[0]
            
        ip = get_ip(hostname)
        country_name, flag = "未知", "🏳"
        if ip and reader:
            match = reader.get(ip)
            if match:
                names = match.get('country', {}).get('names', {})
                country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                flag = get_flag(match.get('country', {}).get('iso_code'))

        new_remark = f"{flag} {country_name} | {protocol} | Windows_me"
        return f"{base_uri}#{quote(new_remark)}"
    except: return uri

def fetch_source(url):
    """抓取并过滤"""
    m_url = mask_url(url)
    try:
        headers = {'User-Agent': random.choice(UA_LIST)}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        
        content = resp.text.strip()
        info = parse_usage_and_expire(content, resp.headers)
        u, d, total = info.get("upload", 0), info.get("download", 0), info.get("total", 0)
        expire = info.get("expire") or info.get("expiration")
        
        if total > 0 and (total - (u + d)) < (1024**3): return []
        if expire and expire > 0 and int(time.time()) >= expire: return []

        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
            
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        nodes = re.findall(pattern, content, re.IGNORECASE)
        print(f"✅ {m_url} (找到 {len(nodes)} 个)")
        return nodes
    except: return []

def generate_clash_yaml(nodes_file_path):
    """生成 Clash 配置文件"""
    yaml_template = f"""port: 7890
socks-port: 7891
allow-lan: true
mode: Rule
log-level: info
ipv6: false
external-controller: :9090

dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - 119.29.29.29
    - 223.5.5.5
  fallback:
    - 8.8.8.8
    - 8.8.4.4
    - tls://1.0.0.1:853
    - tls://dns.google:853

proxy-providers:
  free-nodes:
    type: file
    path: ./nodes.txt
    health-check:
      enable: true
      url: http://www.gstatic.com/generate_204
      interval: 300

proxy-groups:
  - name: 🚀 节点选择
    type: select
    proxies:
      - ⚡ 自动测速
      - DIRECT
    use:
      - free-nodes

  - name: ⚡ 自动测速
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    use:
      - free-nodes

rules:
  - GEOIP,LAN,DIRECT
  - GEOIP,CN,DIRECT
  - MATCH,🚀 节点选择
"""
    return yaml_template

def main():
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links:
        print("❌ 未发现 LINK ")
        return

    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    unique_uris = list(set(all_uris))
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        reader = maxminddb.open_database('GeoLite2-Country.mmdb')
    
    final_nodes = [rename_node(uri, reader) for uri in unique_uris]
    if reader: reader.close()

    os.makedirs('data', exist_ok=True)
    
    # 保存原始节点列表 (供 Clash 的 proxy-providers 使用)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes))
    
    # 保存 V2Ray Base64 格式
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64_content = base64.b64encode('\n'.join(final_nodes).encode('utf-8')).decode('utf-8')
        f.write(b64_content)
    
    # 保存 Clash 配置
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write(generate_clash_yaml('nodes.txt'))

    print(f"\n✨ 任务完成！有效节点: {len(unique_uris)}")
    print(f"💾 已生成: nodes.txt, v2ray.txt, clash.yaml")

if __name__ == "__main__":
    main()
