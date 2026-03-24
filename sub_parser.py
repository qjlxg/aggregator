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
    "Surfboard/2.19.2",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def mask_url(url):
   
    if not url: return "Unknown"
    return f"{url[:3]}***"

def get_flag(code):
    """根据 ISO 国家代码转为 Emoji 国旗"""
    if not code or len(code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def decode_base64(data):
    """通用的 Base64 解码，支持自动补全补丁"""
    if not data: return ""
    try:
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

def get_ip(hostname):
    """带字典缓存的 DNS 解析，减少重复请求"""
    if not hostname: return None
    # 检查是否本身就是 IP
    if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', hostname):
        return hostname
    if hostname in dns_cache: 
        return dns_cache[hostname]
    try:
        # 设置解析超时防止挂死
        ip = socket.gethostbyname(hostname)
        dns_cache[hostname] = ip
        return ip
    except:
        return None

def parse_usage_and_expire(text, headers):
    """解析流量和到期时间 (从 Header 或 Body)"""
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
    except: pass

    if not info:
        for item in text.replace("\n", ";").split(";"):
            if "=" in item:
                parts = item.split("=", 1)
                if len(parts) == 2:
                    k, v = parts
                    try: info[k.strip().lower()] = int(v.strip())
                    except: pass
    return info

def rename_node(uri, reader):
    """

    """
    try:
        # 1. 彻底剥离原始 URI 的备注（# 之后的部分）
        base_uri = uri.split('#')[0] if '#' in uri else uri
        parsed = urlparse(base_uri)
        
        # 2. 识别协议
        protocol = parsed.scheme.upper()
        if protocol == "HYSTERIA2": protocol = "HY2"
        
        # 3. 提取 Hostname (兼容 SS/SSR 格式)
        hostname = parsed.hostname
        if not hostname and "@" in parsed.netloc:
            hostname = parsed.netloc.split("@")[-1].split(":")[0]
            
        # 4. 获取地理位置
        ip = get_ip(hostname)
        country_name, flag = "未知", "🏳"
        
        if ip and reader:
            try:
                match = reader.get(ip)
                if match:
                    names = match.get('country', {}).get('names', {})
                    country_name = names.get('zh-CN', names.get('en', 'Unknown'))
                    iso_code = match.get('country', {}).get('iso_code')
                    flag = get_flag(iso_code)
            except Exception as e:
                # 日志记录 MMDB 异常但不中断流程
                print(f"DEBUG: MMDB lookup fail for {ip}: {e}")

        # 5. 重新生成备注并 URL 编码 (解决 V2RayN 等客户端特殊字符兼容性)
        new_remark = f"{flag} {country_name} | {protocol} | Windows_me"
        return f"{base_uri}#{quote(new_remark)}"
    except:
        return uri

def fetch_source(url):
    """抓取源并进行流量/到期过滤"""
    m_url = mask_url(url)
    try:
        headers = {'User-Agent': random.choice(UA_LIST)}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"❌ 访问失败 [{resp.status_code}]: {m_url}")
            return []
        
        content = resp.text.strip()
        info = parse_usage_and_expire(content, resp.headers)
        
        # --- 校验逻辑 ---
        u, d = info.get("upload", 0), info.get("download", 0)
        total = info.get("total", 0)
        expire = info.get("expire") or info.get("expiration")
        
        # 1. 流量校验 (剩余不足 1GB 则排除)
        THRESHOLD_1GB = 1024 * 1024 * 1024
        if total > 0:
            if (total - (u + d)) < THRESHOLD_1GB:
                print(f"⚠️ 流量耗尽: {m_url}")
                return []

        # 2. 到期校验
        if expire and expire > 0 and int(time.time()) >= expire:
            print(f"⏰ 订阅过期: {m_url}")
            return []

        # --- 提取节点 ---
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded
            
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks)://[^\s\'"<>]+'
        nodes = re.findall(pattern, content, re.IGNORECASE)
        print(f"✅ 成功提取 {len(nodes)} 个节点: {m_url}")
        return nodes
    except Exception as e:
        print(f"💥 抓取异常 {m_url}: {str(e)[:30]}")
        return []

def main():
   
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    if not links:
        print("❌ 未检测到 LINK")
        return

    print(f"🔄 正在处理 {len(links)} 个源，已开启 DNS 缓存与协议优化...")
    
    all_uris = []
    # 20 线程并发抓取
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_source, links))
        for r in results:
            if r: all_uris.extend(r)
    
    # 节点去重
    unique_uris = list(set(all_uris))
    
    # 加载地理位置数据库
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        try:
            reader = maxminddb.open_database('GeoLite2-Country.mmdb')
        except Exception as e:
            print(f"❌ 数据库加载失败: {e}")
    else:
        print("⚠️ 未找到 GeoLite2-Country.mmdb，将无法识别国家信息。")
    
    # 重命名与清洗
    final_nodes = []
    for uri in unique_uris:
        final_nodes.append(rename_node(uri, reader))
    
    if reader: reader.close()

    # 存储结果
    os.makedirs('data', exist_ok=True)
    # 1. 明文格式
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_nodes))
    
    # 2. Base64 订阅格式
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64_content = base64.b64encode('\n'.join(final_nodes).encode('utf-8')).decode('utf-8')
        f.write(b64_content)

    print(f"\n✨ 任务完成！")
    print(f"📊 原始节点总数: {len(all_uris)}")
    print(f"💎 过滤/去重后有效节点: {len(unique_uris)}")
    print(f"💾 结果已保存至 data/ 目录")

if __name__ == "__main__":
    main()
