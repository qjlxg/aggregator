import requests
import re
import os
import base64
import yaml
import json

# 定义支持的节点协议
PROTOCOLS = [
    'vless://', 'vmess://', 'trojan://', 'ss://', 'ssr://',
    'wireguard://', 'grpc://', 'snell://', 'hysteria://',
    'hysteria2://', 'tuic://', 'juicity://'
]

def extract_nodes_from_content(content, content_type='plain'):
    """根据内容类型提取节点信息"""
    nodes = set()
    if content_type == 'base64':
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            for line in decoded_content.splitlines():
                line = line.strip()
                if any(line.startswith(proto) for proto in PROTOCOLS):
                    nodes.add(line)
        except Exception as e:
            print(f"Base64 解码失败: {e}")
    elif content_type == 'yaml':
        try:
            data = yaml.safe_load(content)
            if 'proxies' in data:
                for proxy in data['proxies']:
                    node_type = proxy.get('type')
                    if node_type == 'vmess':
                        # 生成 vmess 节点链接
                        vmess_dict = {
                            "v": "2",
                            "ps": proxy.get('name'),
                            "add": proxy.get('server'),
                            "port": proxy.get('port'),
                            "id": proxy.get('uuid'),
                            "aid": proxy.get('alterId', 0),
                            "scy": proxy.get('cipher', 'auto'),
                            "net": proxy.get('network', 'tcp'),
                            "type": "none",
                            "host": proxy.get('ws-opts', {}).get('headers', {}).get('Host', ''),
                            "path": proxy.get('ws-opts', {}).get('path', ''),
                            "tls": "tls" if proxy.get('tls') else ""
                        }
                        vmess_str = json.dumps(vmess_dict)
                        node_str = f"vmess://{base64.urlsafe_b64encode(vmess_str.encode()).decode().rstrip('=')}"
                        nodes.add(node_str)
                    elif node_type == 'vless':
                        # 生成 vless 节点链接
                        encryption = proxy.get('encryption', 'none')
                        security = 'tls' if proxy.get('tls') else 'none'
                        sni = proxy.get('sni', '')
                        fp = proxy.get('client-fingerprint', 'chrome')
                        network = proxy.get('network', 'tcp')
                        host = proxy.get('ws-opts', {}).get('headers', {}).get('Host', '') if network == 'ws' else ''
                        path = proxy.get('ws-opts', {}).get('path', '') if network == 'ws' else ''
                        node_str = (
                            f"vless://{proxy.get('uuid')}@{proxy.get('server')}:{proxy.get('port')}?"
                            f"encryption={encryption}&security={security}&sni={sni}&fp={fp}&type={network}"
                            f"&host={host}&path={path}"
                        )
                        nodes.add(node_str)
                    elif node_type == 'trojan':
                        # 生成 trojan 节点链接
                        sni = proxy.get('sni', '')
                        node_str = f"trojan://{proxy.get('password')}@{proxy.get('server')}:{proxy.get('port')}?sni={sni}"
                        nodes.add(node_str)
                    elif node_type == 'ss':
                        # 生成 ss 节点链接
                        method = proxy.get('cipher')
                        password = proxy.get('password')
                        auth_str = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip('=')
                        node_str = f"ss://{auth_str}@{proxy.get('server')}:{proxy.get('port')}"
                        nodes.add(node_str)
                    elif node_type == 'hysteria2':
                        # 生成 hysteria2 节点链接
                        node_str = (
                            f"hysteria2://{proxy.get('password')}@"
                            f"{proxy.get('server')}:{proxy.get('port')}?"
                            f"sni={proxy.get('sni')}"
                        )
                        nodes.add(node_str)
                    elif node_type == 'snell':
                        # 生成 snell 节点链接
                        obfs = proxy.get('obfs-opts', {}).get('obfs', 'http')
                        node_str = f"snell://{proxy.get('server')}:{proxy.get('port')}?psk={proxy.get('psk')}&obfs={obfs}"
                        nodes.add(node_str)
                    elif node_type == 'tuic':
                        # 生成 tuic 节点链接
                        node_str = (
                            f"tuic://{proxy.get('uuid')}:{proxy.get('password')}@"
                            f"{proxy.get('server')}:{proxy.get('port')}"
                        )
                        nodes.add(node_str)
        except yaml.YAMLError as e:
            print(f"YAML 解析失败: {e}")
    else:  # 默认按纯文本处理
        for line in content.splitlines():
            line = line.strip()
            if any(line.startswith(proto) for proto in PROTOCOLS):
                nodes.add(line)
    return list(nodes)

def process_url_for_nodes(url, retries=3, timeout=10):
    """处理单个 URL，提取节点，并显示提取到的节点数量"""
    extracted_nodes = set()
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            content = response.text

            if 'text/plain' in content_type:
                if re.match(r'^[A-Za-z0-9+/=]+$', content.strip()):
                    extracted_nodes.update(extract_nodes_from_content(content, 'base64'))
                else:
                    extracted_nodes.update(extract_nodes_from_content(content, 'plain'))
            elif 'yaml' in content_type or url.endswith('.yaml'):
                extracted_nodes.update(extract_nodes_from_content(content, 'yaml'))
            else:
                links = re.findall(r'(https?://[^\s]+)', content)
                for link in links:
                    try:
                        node_response = requests.get(link, timeout=timeout)
                        node_response.raise_for_status()
                        node_content = node_response.text
                        node_content_type = node_response.headers.get('Content-Type', '')
                        if 'text/plain' in node_content_type:
                            if re.match(r'^[A-Za-z0-9+/=]+$', node_content.strip()):
                                extracted_nodes.update(extract_nodes_from_content(node_content, 'base64'))
                            else:
                                extracted_nodes.update(extract_nodes_from_content(node_content, 'plain'))
                        elif 'yaml' in node_content_type or link.endswith('.yaml'):
                            extracted_nodes.update(extract_nodes_from_content(node_content, 'yaml'))
                    except requests.exceptions.RequestException:
                        pass
            break
        except requests.exceptions.RequestException as e:
            print(f"尝试 {attempt+1}/{retries} 失败: {url} - {e}")
            if attempt == retries - 1:
                print(f"无法访问或解析 {url}")
    print(f"从 {url} 提取到 {len(extracted_nodes)} 个节点")
    return list(extracted_nodes)

def save_nodes_to_file(nodes, filename="data/ji.txt"):
    """将节点保存到文件，每行一个节点"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        for node in sorted(list(nodes)):
            f.write(node + "\n")
    print(f"成功保存 {len(nodes)} 个唯一节点到 {filename}")

if __name__ == "__main__":
    main_urls = [
        "https://github.com/qjlxg/TV/raw/refs/heads/main/url/igdux.top.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/clash.yaml",
    ]

    all_extracted_nodes = set()
    for url in main_urls:
        print(f"正在处理 URL: {url}")
        nodes_from_url = process_url_for_nodes(url)
        all_extracted_nodes.update(nodes_from_url)

    unique_nodes = sorted(list(all_extracted_nodes))
    print(f"共提取到 {len(all_extracted_nodes)} 个节点，{len(unique_nodes)} 个唯一节点。")
    save_nodes_to_file(unique_nodes)
