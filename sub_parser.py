import os
import re
import base64
import json
import requests
import yaml
import hashlib
import geoip2.database
import socket
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote

# 配置
LINK = os.environ.get('LINK', '')
OUTPUT_DIR = 'data'
GEOIP_DB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def download_geoip():
    if not os.path.exists(GEOIP_DB_PATH):
        print("正在下载 GeoIP 数据库...")
        r = requests.get(GEOIP_DB_URL, timeout=30)
        with open(GEOIP_DB_PATH, 'wb') as f:
            f.write(r.content)

def get_country(address, reader):
    try:
        # 如果是域名，先解析 IP
        ip = address
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", address):
            ip = socket.gethostbyname(address)
        response = reader.country(ip)
        return response.country.names.get('zh-CN', response.country.name) or "Unknown"
    except:
        return "UN"

def get_md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:6]

def safe_base64_decode(s):
    try:
        # 补齐长度
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except:
        return ""

def parse_uri(uri):
    """通用解析器：将 URI 转换为字典信息"""
    try:
        scheme = uri.split('://')[0].lower()
        content = uri.split('://')[1]
        
        info = {'type': scheme, 'original': uri}
        
        if scheme == 'vmess':
            data = json.loads(safe_base64_decode(content))
            info.update({
                'server': data.get('add'),
                'port': int(data.get('port', 443)),
                'uuid': data.get('id'),
                'aid': int(data.get('aid', 0)),
                'scy': data.get('scy', 'auto'),
                'net': data.get('net', 'tcp'),
                'host': data.get('host', ''),
                'path': data.get('path', ''),
                'tls': True if data.get('tls') == 'tls' else False,
                'sni': data.get('sni', ''),
                'name': data.get('ps', 'vmess')
            })
        elif scheme in ['vless', 'trojan', 'ss', 'hysteria2', 'hy2', 'tuic']:
            # 处理带 # 的备注
            if '#' in content:
                content, name = content.split('#', 1)
                info['name'] = unquote(name)
            
            parsed = urlparse(scheme + "://" + content)
            info['server'] = parsed.hostname
            info['port'] = parsed.port
            
            # 提取用户信息 (uuid, password 等)
            if '@' in parsed.netloc:
                info['userinfo'] = unquote(parsed.netloc.split('@')[0])
            
            # 提取查询参数
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            info.update(params)
            
        return info
    except Exception as e:
        print(f"解析失败: {uri[:30]}... 错误: {e}")
        return None

def build_clash_proxy(info, new_name):
    """根据解析的信息构建 Clash 代理字典"""
    p = {"name": new_name, "server": info['server'], "port": info['port']}
    t = info['type']

    try:
        if t == 'vmess':
            p.update({
                "type": "vmess", "uuid": info['uuid'], "alterId": info['aid'],
                "cipher": info['scy'], "network": info['net'],
                "tls": info['tls'], "udp": True
            })
            if info['net'] in ['ws', 'grpc']:
                p[f"{info['net']-opts}"] = {"path": info['path'], "headers": {"Host": info['host']}}
        
        elif t == 'vless':
            p.update({
                "type": "vless", "uuid": info['userinfo'], "udp": True,
                "tls": True if info.get('security') in ['tls', 'reality'] else False,
                "flow": info.get('flow', ''), "servername": info.get('sni', '')
            })
        
        elif t == 'trojan':
            p.update({"type": "trojan", "password": info['userinfo'], "udp": True, "sni": info.get('sni', '')})
        
        elif t == 'ss':
            # 兼容 ss://method:password@host:port
            if ':' in info.get('userinfo', ''):
                p["cipher"], p["password"] = info['userinfo'].split(':', 1)
            p["type"] = "ss"
            
        elif t in ['hysteria2', 'hy2']:
            p.update({"type": "hysteria2", "password": info['userinfo'], "sni": info.get('sni', ''), "alpn": ["h3"]})
        
        return p
    except:
        return None

def run():
    download_geoip()
    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    
    # 获取内容并尝试 Base64 解码
    print("获取订阅内容...")
    raw_response = requests.get(LINK, timeout=15).text
    decoded_content = safe_base64_decode(raw_response)
    content = decoded_content if decoded_content else raw_response
    
    # 提取所有 URI
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    uris = re.findall(pattern, content)
    
    clash_proxies = []
    final_uris = []
    
    for index, uri in enumerate(uris):
        info = parse_uri(uri)
        if not info or not info.get('server'): continue
        
        # 定位与更名
        country = get_country(info['server'], reader)
        md5_tag = get_md5(uri + str(index))
        new_name = f"{country}_{index + 1}_{md5_tag}"
        
        # 构建 Clash 格式
        cp = build_clash_proxy(info, new_name)
        if cp: clash_proxies.append(cp)
        
        # 更新 URI 中的备注部分用于 nodes.txt
        if '#' in uri:
            base_uri = uri.split('#')[0]
            final_uris.append(f"{base_uri}#{new_name}")
        else:
            final_uris.append(f"{uri}#{new_name}")

    reader.close()

    # 写入文件
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False)
    
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | {update_time}\n" + "\n".join(final_uris) + "\n")
    
    b64_content = base64.b64encode(("\n".join(final_uris)).encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"成功！保存了 {len(clash_proxies)} 个节点到 {OUTPUT_DIR} 目录")

if __name__ == "__main__":
    run()
