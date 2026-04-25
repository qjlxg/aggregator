import asyncio
import aiohttp
import base64
import re
import csv
import os
import socket
import json
import yaml  # 需要安装: pip install pyyaml
import hashlib
from datetime import datetime
from urllib.parse import urlparse, quote
import geoip2.database

# --- 基础配置 ---
OUTPUT_DIR = "data"  
GEOIP_DB = "GeoLite2-Country.mmdb" 

MAX_CONCURRENT_TASKS = 500 
MAX_RETRIES = 1

# --- 排除过滤名单 ---
BLACKLIST_KEYWORDS = ["ly.ba000.cc", "wocao.su7.me", "jiasu01.vip", "louwangzhiyu", "mojie"]

# --- 工具函数 ---
def decode_base64(data):
    if not data: return ""
    try:
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        decoded_bytes = base64.b64decode(clean_data)
        for encoding in ['utf-8', 'gbk', 'latin-1']:
            try: return decoded_bytes.decode(encoding)
            except: continue
        return decoded_bytes.decode('utf-8', errors='ignore')
    except: return ""

def encode_base64(data):
    try: return base64.b64encode(data.encode('utf-8')).decode('utf-8')
    except: return ""

def get_md5_short(text):
    return hashlib.md5(text.encode()).hexdigest()[:4]

def get_geo_info(host, reader):
    if not host or not reader: return "🌐", "未知地区"
    ip = host
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        try: ip = socket.gethostbyname(host)
        except: return "🚩", "解析失败"
    try:
        res = reader.country(ip)
        code = res.country.iso_code
        flag = "".join(chr(ord(c) + 127397) for c in code.upper()) if code else "🌐"
        country_name = res.country.names.get('zh-CN') or res.country.name or "未知国家"
        return flag, country_name
    except: return "🌐", "未知地区"

def get_node_details(line, protocol):
    try:
        if protocol == 'vmess':
            v = json.loads(decode_base64(line.split("://")[1]))
            return {"server": v.get('add'), "port": int(v.get('port', 443)), "uuid": v.get('id'), "tls": v.get('tls') == "tls"}
        match = re.search(r'@([^:/#?]+):(\d+)', line)
        if match: return {"server": match.group(1), "port": int(match.group(2))}
        u = urlparse(line)
        host = u.hostname
        if not host and "@" in u.netloc:
            host = u.netloc.split("@")[-1].split(":")[0]
        return {"server": host, "port": int(u.port or 443)}
    except: return None

def parse_nodes(content, reader):
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2']
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>#]+(?:#[^\s\"\'<>]*)?'
    
    # 首先尝试直接解析内容中的节点
    found_links = re.findall(pattern, content, re.IGNORECASE)
    
    # 如果没直接找到节点，且内容看起来像 Base64（订阅文件常用格式），解码后再试一次
    if not found_links:
        decoded = decode_base64(content)
        if decoded:
            found_links = re.findall(pattern, decoded, re.IGNORECASE)
    
    nodes = []
    for link in found_links:
        protocol = link.split("://")[0].lower()
        try:
            if protocol == 'vmess':
                host = json.loads(decode_base64(link.split("://")[1])).get('add')
            else:
                match = re.search(r'@([^:/#?]+)', link)
                host = match.group(1).split(':')[0] if match else urlparse(link).hostname
            
            if not host or any(k in host.lower() for k in BLACKLIST_KEYWORDS): continue
            flag, country = get_geo_info(host, reader)
            nodes.append({"protocol": protocol, "flag": flag, "country": country, "line": link})
        except: continue
    return nodes

async def fetch_with_retry(session, url, reader, semaphore):
    async with semaphore:
        for _ in range(MAX_RETRIES + 1):
            try:
                async with session.get(url, timeout=15, ssl=False) as res:
                    if res.status != 200: continue
                    text = await res.text()
                    nodes = parse_nodes(text, reader)
                    if nodes: return url, nodes, len(nodes)
            except: pass
        return url, [], 0

# --- 主逻辑 ---
async def main():
    if not os.path.exists(GEOIP_DB):
        print(f"缺失 {GEOIP_DB} 库文件"); return
    
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)

    # 1. 获取环境变量
    link_env = os.environ.get('LINK', '').strip()
    if not link_env:
        print("未检测到环境变量 LINK。")
        return

    raw_node_objs = [] 
    links_to_fetch = []

    with geoip2.database.Reader(GEOIP_DB) as reader:
        # 2. 预处理：解析 LINK 中的 URL 和 直接节点内容
        lines = link_env.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            # 如果是 http 开头的网址，加入待抓取列表
            if line.startswith('http'):
                links_to_fetch.append(line)
        
        # 无论是否有 URL，都把整个 link_env 丢进 parse_nodes 
        # 这样可以直接提取出变量中粘贴的明文节点或 Base64 节点内容
        raw_node_objs.extend(parse_nodes(link_env, reader))

        # 3. 处理远程订阅 URL
        if links_to_fetch:
            print(f"--- 正在从 {len(links_to_fetch)} 个订阅源获取节点 ---")
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
            async with aiohttp.ClientSession(headers={'User-Agent': 'v2rayN/6.23'}) as session:
                tasks = [fetch_with_retry(session, url, reader, semaphore) for url in links_to_fetch]
                results = await asyncio.gather(*tasks)
                for url, nodes, count in results:
                    raw_node_objs.extend(nodes)

    if not raw_node_objs:
        print("未发现任何有效节点。")
        return

    # --- 节点处理（无去重） ---
    final_uris = []
    clash_proxies = []
    
    for index, obj in enumerate(raw_node_objs):
        line, protocol, flag, country = obj["line"], obj["protocol"], obj["flag"], obj["country"]
        base_link = line.split('#')[0] if protocol != 'vmess' else line

        # 使用 index 和 时间戳生成唯一后缀，确保即使节点内容完全一样，在 Clash 配置文件里也不会冲突
        unique_id = get_md5_short(f"{line}_{index}_{datetime.now().timestamp()}")
        new_name = f"{flag} {country} {unique_id}"
        
        try:
            # 更新节点备注名
            if protocol == 'vmess':
                v_json = json.loads(decode_base64(line.split("://")[1]))
                v_json['ps'] = new_name
                final_uris.append(f"vmess://{encode_base64(json.dumps(v_json))}")
            elif protocol == 'ssr':
                ssr_body = decode_base64(line.split("://")[1])
                main_part = ssr_body.split('&remarks=')[0]
                new_rem = encode_base64(new_name).replace('=', '').replace('+', '-').replace('/', '_')
                final_uris.append(f"ssr://{encode_base64(main_part + '&remarks=' + new_rem)}")
            else:
                final_uris.append(f"{base_link}#{quote(new_name)}")

            # 转换为 Clash 代理项
            d = get_node_details(line, protocol)
            if d:
                proxy_item = {
                    "name": new_name,
                    "type": "trojan" if protocol == 'anytls' else protocol,
                    "server": d['server'],
                    "port": d['port'],
                    "udp": True
                }
                if protocol == 'vmess':
                    proxy_item.update({"uuid": d['uuid'], "cipher": "auto", "tls": d['tls']})
                clash_proxies.append(proxy_item)
        except: continue

    # --- 保存结果 ---
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clash YAML
    full_config = {
        "port": 7890,
        "mode": "Rule",
        "dns": {"enable": True, "nameserver": ["119.29.29.29", "223.5.5.5"]},
        "proxies": clash_proxies
    }
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'# Last Updated: {update_time}\n# Total Nodes: {len(clash_proxies)}\n\n')
        yaml.safe_dump(full_config, f, allow_unicode=True, sort_keys=False, indent=2)
    
    # 明文 nodes.txt
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    # Base64 v2ray.txt
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"--- 处理完成！节点总数: {len(final_uris)}，已保存至 {OUTPUT_DIR} ---")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
