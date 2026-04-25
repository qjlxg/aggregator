import asyncio
import aiohttp
import base64
import re
import os
import socket
import json
import yaml  # 需要安装: pip install pyyaml
import hashlib
from datetime import datetime
from urllib.parse import urlparse, quote, unquote
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
    # 判断是否为IP，如果不是则尝试解析DNS
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
    """
    提取服务器地址和端口，用于 GeoIP 查询及 Clash 生成
    """
    try:
        if protocol == 'vmess':
            v = json.loads(decode_base64(line.split("://")[1]))
            return {"server": v.get('add'), "port": int(v.get('port', 443)), "uuid": v.get('id'), "tls": v.get('tls') == "tls"}
        
        # 处理带 @ 符号的协议 (ss, vless, trojan, hysteria2, tuic etc.)
        match = re.search(r'@([^:/#?]+):(\d+)', line)
        if match: return {"server": match.group(1), "port": int(match.group(2))}
        
        # 通用解析
        u = urlparse(line)
        host = u.hostname
        if not host and "@" in u.netloc:
            host = u.netloc.split("@")[-1].split(":")[0]
        return {"server": host, "port": int(u.port or 443)}
    except: return None

def parse_nodes(content, reader):
    """
    支持几乎所有已知协议的正则表达式
    """
    protocols = [
        'vmess', 'vless', 'trojan', 'ss', 'ssr', 
        'hysteria2', 'hy2', 'tuic', 'juicity', 
        'snell', 'socks', 'http', 'https'
    ]
    # 构建更强大的正则：匹配协议头直到空格、引号、尖括号或行尾
    pattern = r'(?:' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    
    # 1. 直接提取
    found_links = re.findall(pattern, content, re.IGNORECASE)
    
    # 2. 如果没找到，尝试整体 Base64 解码后再提取
    if not found_links:
        decoded = decode_base64(content)
        if decoded:
            found_links = re.findall(pattern, decoded, re.IGNORECASE)
    
    nodes = []
    for link in found_links:
        # 清洗链接（去除末尾可能的冗余字符）
        link = link.strip().split('\\')[0].split('"')[0]
        protocol = link.split("://")[0].lower()
        
        try:
            # 提取 Host 用于 GeoIP 识别
            details = get_node_details(link, protocol)
            if not details or not details.get('server'): continue
            
            host = details['server']
            if any(k in host.lower() for k in BLACKLIST_KEYWORDS): continue
            
            flag, country = get_geo_info(host, reader)
            nodes.append({
                "protocol": protocol, 
                "flag": flag, 
                "country": country, 
                "line": link,
                "details": details
            })
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

    link_env = os.environ.get('LINK', '').strip()
    if not link_env:
        print("未检测到环境变量 LINK。")
        return

    raw_node_objs = [] 
    links_to_fetch = []

    with geoip2.database.Reader(GEOIP_DB) as reader:
        # 1. 识别 LINK 中的 URL 任务
        lines = link_env.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('http'):
                links_to_fetch.append(line)
        
        # 2. 直接从 LINK 变量中提取已有的节点信息
        raw_node_objs.extend(parse_nodes(link_env, reader))

        # 3. 异步抓取订阅链接
        if links_to_fetch:
            print(f"--- 正在处理 {len(links_to_fetch)} 个订阅源 ---")
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
            async with aiohttp.ClientSession(headers={'User-Agent': 'v2rayN/6.23'}) as session:
                tasks = [fetch_with_retry(session, url, reader, semaphore) for url in links_to_fetch]
                results = await asyncio.gather(*tasks)
                for _, nodes, _ in results:
                    raw_node_objs.extend(nodes)

    if not raw_node_objs:
        print("未发现有效节点。")
        return

    # --- 封装输出（无去重逻辑） ---
    final_uris = []
    clash_proxies = []
    
    for i, obj in enumerate(raw_node_objs):
        line, protocol = obj["line"], obj["protocol"]
        flag, country = obj["flag"], obj["country"]
        
        # 移除原有的备注信息（#后的内容）
        base_link = line.split('#')[0] if protocol != 'vmess' else line
        
        # 生成唯一备注名
        unique_suffix = get_md5_short(f"{line}{i}{datetime.now()}")
        new_name = f"{flag} {country} | {protocol.upper()}_{i+1}_{unique_suffix}"
        
        try:
            # 协议特定备注修改
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

            # Clash 兼容逻辑 (目前支持主流协议，Tuic/Hy2等需最新Clash核心)
            d = obj["details"]
            if d:
                proxy_item = {
                    "name": new_name,
                    "type": protocol if protocol != 'hy2' else 'hysteria2',
                    "server": d['server'],
                    "port": d['port'],
                    "udp": True
                }
                if protocol == 'vmess':
                    proxy_item.update({"uuid": d['uuid'], "cipher": "auto", "tls": d['tls']})
                clash_proxies.append(proxy_item)
        except: continue

    # --- 保存 ---
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clash
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'# Nodes: {len(clash_proxies)}\n# Update: {update_time}\n')
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False)
    
    # 订阅格式
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write("\n".join(final_uris))
    
    b64_nodes = base64.b64encode(("\n".join(final_uris)).encode()).decode()
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_nodes)

    print(f"--- 任务完成！总计解析节点: {len(final_uris)} ---")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
