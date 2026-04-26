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
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"  # 使用根目录已有的文件

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def get_country(address, reader):
    try:
        ip = address
        # 如果是域名，尝试解析为 IP
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", address):
            ip = socket.gethostbyname(address)
        response = reader.country(ip)
        return response.country.names.get('zh-CN', response.country.name) or "Unknown"
    except:
        return "Unknown"

def get_md5(content):
    return hashlib.md5(content.encode()).hexdigest()[:6]

def safe_base64_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        missing_padding = len(s) % 4
        if missing_padding:
            s += '=' * (4 - missing_padding)
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except:
        return ""

def parse_uri(uri):
    """解析各种协议 URI 并提取核心信息"""
    try:
        scheme = uri.split('://')[0].lower()
        parts = uri.split('://')[1]
        info = {'type': scheme, 'original': uri}

        if scheme == 'vmess':
            data = json.loads(safe_base64_decode(parts))
            info.update({
                'server': data.get('add'), 'port': int(data.get('port', 443)),
                'uuid': data.get('id'), 'aid': int(data.get('aid', 0)),
                'net': data.get('net', 'tcp'), 'tls': data.get('tls'),
                'sni': data.get('sni', ''), 'path': data.get('path', ''),
                'host': data.get('host', '')
            })
        else:
            # 处理带备注的格式
            raw_uri = uri
            remark = ""
            if '#' in parts:
                parts, remark = parts.split('#', 1)
                remark = unquote(remark)
            
            parsed = urlparse(scheme + "://" + parts)
            info['server'] = parsed.hostname
            info['port'] = parsed.port or 443
            info['userinfo'] = unquote(parsed.netloc.split('@')[0]) if '@' in parsed.netloc else ""
            
            # 提取查询参数 (sni, flow, security, etc.)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            info.update(params)
        return info
    except:
        return None

def build_clash_proxy(info, name):
    """将解析信息转换为 Clash 代理配置"""
    try:
        t = info['type']
        base = {"name": name, "server": info['server'], "port": int(info['port'])}
        
        if t == 'vmess':
            base.update({
                "type": "vmess", "uuid": info['uuid'], "alterId": info['aid'],
                "cipher": "auto", "udp": True, "tls": True if info['tls'] == 'tls' else False,
                "network": info['net'], "servername": info['sni'] or info['server']
            })
            if info['net'] in ['ws', 'grpc']:
                key = f"{info['net']}-opts"
                base[key] = {"path": info['path'], "headers": {"Host": info['host']}}
        
        elif t == 'vless':
            base.update({
                "type": "vless", "uuid": info['userinfo'], "udp": True,
                "tls": True if info.get('security') in ['tls', 'reality'] else False,
                "servername": info.get('sni', ''), "flow": info.get('flow', '')
            })
        
        elif t == 'ss' or t == 'shadowsocks':
            base["type"] = "ss"
            if ':' in info['userinfo']:
                base["cipher"], base["password"] = info['userinfo'].split(':', 1)
        
        elif t == 'trojan':
            base.update({"type": "trojan", "password": info['userinfo'], "udp": True, "sni": info.get('sni', '')})
        
        elif t in ['hysteria2', 'hy2']:
            base.update({"type": "hysteria2", "password": info['userinfo'], "sni": info.get('sni', ''), "alpn": ["h3"]})
            
        elif t == 'tuic':
            base.update({"type": "tuic", "uuid": info['userinfo'], "sni": info.get('sni', ''), "alpn": ["h3"]})

        return base
    except:
        return None

def main():
    if not LINK:
        print("错误: 请设置 LINK 环境变量")
        return

    # 获取内容
    resp = requests.get(LINK, timeout=15).text
    # 尝试解密整个订阅内容
    decoded = safe_base64_decode(resp)
    content = decoded if "://" in decoded else resp
    
    protocols = ['vmess', 'vless', 'trojan', 'ss', 'ssr', 'hysteria2', 'hy2', 'tuic', 'juicity', 'snell', 'socks', 'shadowsocks']
    pattern = r'(' + '|'.join(protocols) + r')://[^\s\"\'<>]+'
    raw_uris = re.findall(pattern, content)

    reader = geoip2.database.Reader(GEOIP_DB_PATH)
    clash_proxies = []
    final_uris = []

    for idx, uri in enumerate(raw_uris):
        info = parse_uri(uri)
        if not info or not info.get('server'):
            continue
        
        # 生成名称: 国家_序号_MD5
        country = get_country(info['server'], reader)
        md5_code = get_md5(uri + str(idx))
        new_name = f"{country}_{idx + 1}_{md5_code}"
        
        # 1. 构造 Clash 代理
        cp = build_clash_proxy(info, new_name)
        if cp:
            clash_proxies.append(cp)
        
        # 2. 构造带新名称的 URI
        clean_uri = uri.split('#')[0]
        final_uris.append(f"{clean_uri}#{new_name}")

    reader.close()

    # 保存结果
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clash YAML
    with open(os.path.join(OUTPUT_DIR, 'clash.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": clash_proxies}, f, allow_unicode=True, sort_keys=False, indent=2)
    
    # Nodes TXT
    with open(os.path.join(OUTPUT_DIR, 'nodes.txt'), 'w', encoding='utf-8') as f:
        f.write(f"# Total: {len(final_uris)} | Updated: {update_time}\n" + "\n".join(final_uris) + "\n")
    
    # V2ray Base64 TXT
    b64_content = base64.b64encode(("\n".join(final_uris) + "\n").encode('utf-8')).decode('utf-8')
    with open(os.path.join(OUTPUT_DIR, 'v2ray.txt'), 'w', encoding='utf-8') as f:
        f.write(b64_content)

    print(f"任务完成！总计提取节点: {len(final_uris)}")

if __name__ == "__main__":
    main()
