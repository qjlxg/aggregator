import asyncio
import aiohttp
import base64
import re
import csv
import os
import socket
import json
import yaml
import hashlib
from datetime import datetime
from urllib.parse import urlparse, quote
import geoip2.database

OUTPUT_DIR = "data"  
GEOIP_DB = "GeoLite2-Country.mmdb" 

MAX_CONCURRENT_TASKS = 500 
MAX_RETRIES = 1

BLACKLIST_KEYWORDS = ["ly.ba000.cc", "wocao.su7.me", "jiasu01.vip", "louwangzhiyu", "mojie"]

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

def parse_nodes(content, reader, exclude_http=False):
    # 完整协议列表
    protocols = [
        'vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 
        'tuic', 'juicity', 'snell', 'socks', 'http', 'https', 'shadowsocks'
    ]
    
    # 如果 exclude_http 为 True，则从匹配协议中移除 http 和 https
    # 这样在解析 LINK 变量时，就不会把你的订阅 URL 当做节点抓出来
    current_protocols = protocols
    if exclude_http:
        current_protocols = [p for p in protocols if p not in ['http', 'https']]

    pattern = r'(?:' + '|'.join(current_protocols) + r')://[^\s\"\'<>#\\]+(?:#[^\s\"\'<>\\]*)?'
    
    found_links = re.findall(pattern, content, re.IGNORECASE)
    
    if not found_links and not exclude_http:
        decoded = decode_base64(content)
        if decoded:
            found_links = re.findall(pattern, decoded, re.IGNORECASE)
    
    nodes = []
    for link in found_links:
        protocol = link.split("://")[0].lower()
        try:
            if protocol == 'vmess':
                v_data = json.loads(decode_base64(link.split("://")[1]))
                host = v_data.get('add')
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
                    # 抓取回来的内容如果是 Base64，在这里会进行解码解析，所以这里不能排除 http 节点（防止嵌套订阅）
                    nodes = parse_nodes(text, reader, exclude_http=False)
                    if nodes: return url, nodes, len(nodes)
            except: pass
        return url, [], 0

async def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    link_env = os.environ.get('LINK', '').strip()

    links_to_fetch = []
    raw_node_objs = [] 

    reader = None
    if os.path.exists(GEOIP_DB):
        reader = geoip2.database.Reader(GEOIP_DB)

    # --- 修正逻辑开始 ---
    # 1. 提取变量中的 URL 用于后续抓取
    urls_in_env = re.findall(r'https?://[^\s,]+', link_env)
    links_to_fetch.extend(urls_in_env)
    
    # 2. 解析变量中的明文节点，但排除 http/https 协议头，防止订阅地址被当成节点输出
    raw_node_objs.extend(parse_nodes(link_env, reader, exclude_http=True))
    # --- 修正逻辑结束 ---

    if links_to_fetch:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        async with aiohttp.ClientSession(headers={'User-Agent': 'v2rayN/6.23'}) as session:
            tasks = [fetch_with_retry(session, url, reader, semaphore) for url in links_to_fetch]
            results = await asyncio.gather(*tasks)
            for url, nodes, count in results:
                raw_node_objs.extend(nodes)

    final_uris = []
    clash_proxies = []
    
    for i, obj in enumerate(raw_node_objs):
        line, protocol, flag, country = obj["line"], obj["protocol"], obj["flag"], obj["country"]
        base_link = line.split('#')[0] if protocol != 'vmess' else line
        short_id = get_md5_short(f"{line}_{i}_{datetime.now().timestamp()}")
        new_name = f"{flag} {country} {short_id}"
        
        try:
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

            d = get_node_details(line, protocol)
            if d:
                proxy_item = {
                    "name": new_name,
                    "type": protocol if protocol not in ['hy2', 'hysteria2'] else 'hysteria2',
                    "server": d['server'],
                    "port": d['port'],
                    "udp": True
                }
                if protocol == 'vmess':
                    proxy_item.update({"uuid": d['uuid'], "cipher": "auto", "tls": d['tls']})
                clash_proxies.append(proxy_item)
        except: continue

    if reader:
        reader.close()

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    full_config = {
        "port": 7890,
        "mode": "Rule",
        "dns": {"enable": True, "nameserver": ["119.29.29.29", "223.5.5.5"]},
        "proxies": clash_proxies
    }
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'# Last Updated: {update_time}\n# Total Nodes: {len(clash_proxies)}\n\n')
        yaml.safe_dump(full_config, f, allow_unicode=True, sort_keys=False, indent=2)
    
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"任务完成！成功提取并转换节点总数: {len(final_uris)}")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
