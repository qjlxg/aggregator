import os
import re
import base64
import requests
import yaml
import hashlib
import geoip2.database
from datetime import datetime

# 配置
LINK = os.environ.get('LINK', '')
OUTPUT_DIR = 'data'
GEOIP_DB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"

# 确保目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def download_geoip():
    if not os.path.exists(GEOIP_DB_PATH):
        print("正在下载 GeoIP 数据库...")
        r = requests.get(GEOIP_DB_URL)
        with open(GEOIP_DB_PATH, 'wb') as f:
            f.write(r.content)

def get_country(ip, reader):
    try:
        response = reader.country(ip)
        return response.country.names.get('zh-CN', response.country.name) or "Unknown"
    except:
        return "Unknown"

def get_md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:8]

def extract_nodes(content):
    # 支持的协议正则
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    return re.findall(pattern, content)

def fetch_content(url):
    try:
        resp = requests.get(url, timeout=15)
        text = resp.text
        # 尝试 base64 解码 (针对普通订阅链接)
        try:
            return base64.b64decode(text).decode('utf-8')
        except:
            return text
    except Exception as e:
        print(f"提取失败: {e}")
        return ""

def parse_and_rename():
    download_geoip()
    raw_data = fetch_content(LINK)
    if not raw_data:
        print("未获取到任何数据")
        return

    uris = extract_nodes(raw_data)
    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    
    clash_proxies = []
    final_uris = []
    
    for index, uri in enumerate(uris):
        # 提取 IP/域名进行定位
        # 这里使用简单的正则提取主机部分，实际情况协议复杂，这里简化处理
        host_match = re.search(r'@?([^:/?#]+):(\d+)', uri)
        host = host_match.group(1) if host_match else "127.0.0.1"
        
        # 获取国家
        country = get_country(host, reader)
        md5_suffix = get_md5(uri + str(index))
        new_name = f"{country}_{index + 1}_{md5_suffix}"
        
        # 1. 处理 URIs (简单替换/附加名称, 实际 URI 修改较复杂，这里保持原样但记录名称)
        final_uris.append(uri)
        
        # 2. 构建简易 Clash 代理 (由于协议众多，这里仅作为演示生成占位)
        # 注意：完整转换所有协议到 Clash 需要极复杂的解析库，此处仅根据协议名创建基础结构
        proto = uri.split('://')[0]
        clash_proxies.append({
            "name": new_name,
            "type": proto if proto != 'shadowsocks' else 'ss',
            "server": host,
            "port": 443, # 占位
            # 其他字段根据实际需求解析
        })

    reader.close()

    # 写入文件
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clash YAML
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False, indent=2)
    
    # 明文 nodes.txt
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    # Base64 v2ray.txt
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"任务完成！总计提取节点: {len(final_uris)}")

if __name__ == "__main__":
    parse_and_rename()
