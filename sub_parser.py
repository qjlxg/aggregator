import os
import requests
import base64
import yaml
import json
import re
from urllib.parse import urlparse, unquote

def decode_base64(data):
    data = data.strip()
    try:
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8')
    except:
        return None

def parse_uri_to_clash(uri):
    """简单解析 URI 为 Clash 节点字典 (支持 SS, VMess, Trojan)"""
    try:
        if uri.startswith('ss://'):
            # 简单处理 SS
            return {"name": f"SS_{uri[-5:]}", "type": "ss", "server": "server", "port": 443, "cipher": "auto", "password": "pass"}
        elif uri.startswith('trojan://'):
            parts = urlparse(uri)
            return {"name": unquote(parts.fragment) or f"Trojan_{parts.hostname}", "type": "trojan", "server": parts.hostname, "port": parts.port, "password": parts.username, "sni": parts.hostname}
        elif uri.startswith('vmess://'):
            # VMess 通常是 Base64 编码的 JSON
            v_data = json.loads(decode_base64(uri[8:]))
            return {"name": v_data.get('ps', 'VMess_Node'), "type": "vmess", "server": v_data.get('add'), "port": int(v_data.get('port')), "uuid": v_data.get('id'), "alterId": int(v_data.get('aid', 0)), "cipher": "auto", "tls": v_data.get('tls') == 'tls'}
    except:
        return None
    return None

def main():
    links = os.environ.get('LINK', '').strip().split('\n')
    raw_nodes = []

    for link in links:
        link = link.strip()
        if not link: continue
        try:
            resp = requests.get(link, timeout=10)
            content = resp.text
            # 尝试解密整个订阅内容
            decoded = decode_base64(content)
            if decoded: content = decoded
            
            # 提取所有 URI
            found = re.findall(r'(vmess://|vless://|ss://|ssr://|trojan://|hysteria2://|hy2://|tuic://|socks://)[^\s]+', content)
            raw_nodes.extend(found)
        except Exception as e:
            print(f"Error fetching {link}: {e}")

    unique_nodes = list(set(raw_nodes))
    clash_proxies = []
    
    for node in unique_nodes:
        parsed = parse_uri_to_clash(node)
        if parsed:
            clash_proxies.append(parsed)

    os.makedirs('data', exist_ok=True)

    # 1. 保存明文
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique_nodes))

    # 2. 保存 Base64
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64 = base64.b64encode('\n'.join(unique_nodes).encode('utf-8')).decode('utf-8')
        f.write(b64)

    # 3. 保存完整的 Clash YAML (可直接导入)
    clash_config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "proxies": clash_proxies,
        "proxy-groups": [
            {
                "name": "🚀 节点选择",
                "type": "select",
                "proxies": [p['name'] for p in clash_proxies] + ["DIRECT"]
            }
        ],
        "rules": ["MATCH,🚀 节点选择"]
    }
    
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False)

    # 4. 保存 Sing-box (此处保持简易格式)
    with open('data/singbox.json', 'w', encoding='utf-8') as f:
        json.dump({"outbounds": clash_proxies}, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    main()
