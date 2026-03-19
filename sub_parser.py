import os, requests, base64, yaml, json, re
from urllib.parse import urlparse, unquote

def decode_base64(data):
    data = data.strip()
    try:
        # 处理可能存在的非Base64字符（如Clash配置文件混入）
        if not re.match(r'^[A-Za-z0-9+/= \n\r]+$', data): return None
        missing_padding = len(data) % 4
        if missing_padding: data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8')
    except: return None

def parse_to_clash_proxy(uri):
    """将 URI 转换为 Clash 节点字典"""
    try:
        uri = uri.strip()
        parsed = urlparse(uri)
        scheme = parsed.scheme
        name = unquote(parsed.fragment) if parsed.fragment else f"{scheme.upper()}_{parsed.hostname[-5:]}"
        
        # 基础结构
        node = {"name": name, "server": parsed.hostname, "port": parsed.port}

        if scheme == 'ss':
            node["type"] = "ss"
            # 处理 ss://method:password@host:port
            if '@' in parsed.netloc:
                userinfo, _ = parsed.netloc.rsplit('@', 1)
                # 有些 SS 链接的 userinfo 也是 base64
                if ':' not in userinfo:
                    userinfo = decode_base64(userinfo)
                method, password = userinfo.split(':', 1)
                node.update({"cipher": method, "password": password})
            return node

        elif scheme == 'trojan':
            node.update({"type": "trojan", "password": parsed.username, "sni": parsed.hostname, "udp": True})
            return node

        elif scheme == 'vmess':
            v_data = json.loads(decode_base64(uri[8:]))
            node.update({
                "name": v_data.get('ps', name),
                "type": "vmess",
                "server": v_data.get('add'),
                "port": int(v_data.get('port')),
                "uuid": v_data.get('id'),
                "alterId": int(v_data.get('aid', 0)),
                "cipher": "auto",
                "tls": v_data.get('tls') == 'tls',
                "network": v_data.get('net', 'tcp')
            })
            return node

        elif scheme in ['hysteria2', 'hy2']:
            node.update({"type": "hysteria2", "password": parsed.username, "sni": parsed.hostname, "alpn": ["h3"]})
            return node
            
        elif scheme == 'vless':
            # 这里的 vless 需要支持 Reality/XTLS 的 Clash 核心才能运行
            node.update({"type": "vless", "uuid": parsed.username, "tls": True, "udp": True})
            return node

    except Exception:
        return None
    return None

def main():
    # 获取变量并分割
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    
    all_raw_uris = []
    
    print(f"--- 正在开始处理，检测到 {len(links)} 个订阅源 ---")

    for idx, link in enumerate(links):
       
        domain = urlparse(link).netloc or f"Source_{idx+1}"
        print(f"正在抓取源 [{idx+1}]: {domain}...")
        
        try:
            resp = requests.get(link, timeout=15)
            if resp.status_code != 200: continue
            
            content = resp.text
            # 识别格式：1. 可能是Base64订阅 2. 可能是明文 3. 可能是YAML
            decoded = decode_base64(content)
            content_to_parse = decoded if decoded else content
            
            # 提取所有支持的协议链接
            pattern = r'(vmess://|vless://|ss://|ssr://|trojan://|hysteria2://|hy2://|tuic://|socks://)[^\s]+'
            found = re.findall(pattern, content_to_parse)
            all_raw_uris.extend(found)
        except:
            print(f"源 {domain} 抓取失败，已跳过")

    # 去重
    unique_uris = list(set(all_raw_uris))
    proxies = []
    for uri in unique_uris:
        p = parse_to_clash_proxy(uri)
        if p: proxies.append(p)

    # 目录准备
    os.makedirs('data', exist_ok=True)

    # 1. 保存明文 (nodes.txt)
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique_uris))

    # 2. 保存 Base64 (v2ray.txt)
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        b64_str = base64.b64encode('\n'.join(unique_uris).encode('utf-8')).decode('utf-8')
        f.write(b64_str)

    # 3. 保存 Clash YAML
    clash_config = {
        "proxies": proxies,
        "proxy-groups": [
            {"name": "🚀 自动选择", "type": "url-test", "proxies": [p['name'] for p in proxies], "url": "http://www.gstatic.com/generate_204", "interval": 300},
            {"name": "🔰 手动选择", "type": "select", "proxies": ["🚀 自动选择"] + [p['name'] for p in proxies]}
        ],
        "rules": ["MATCH,🔰 手动选择"]
    }
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(clash_config, f, allow_unicode=True, sort_keys=False)

    # 4. 保存 Sing-box JSON
    sb_config = {"outbounds": proxies} # 简化处理
    with open('data/singbox.json', 'w', encoding='utf-8') as f:
        json.dump(sb_config, f, indent=4, ensure_ascii=False)

    print(f"--- 处理结束：共解析有效节点 {len(proxies)} 个 ---")

if __name__ == "__main__":
    main()
