import requests
import re
import os
import base64
import yaml

def extract_nodes_from_content(content, content_type='plain'):
    """根据内容类型提取节点信息"""
    nodes = set()
    node_patterns = [
        r'vless://[^\s]+',
        r'vmess://[^\s]+',
        r'trojan://[^\s]+',
        r'ss://[^\s]+',
        r'ssr://[^\s]+',
        r'wireguard://[^\s]+',
        r'grpc://[^\s]+',
        r'snell://[^\s]+',
        r'hysteria://[^\s]+',
        r'hysteria2://[^\s]+',
        r'tuic://[^\s]+',
        r'juicity://[^\s]+',
    ]

    if content_type == 'base64':
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            for pattern in node_patterns:
                found_nodes = re.findall(pattern, decoded_content)
                nodes.update(found_nodes)
        except Exception as e:
            print(f"Base64 解码失败: {e}")
    elif content_type == 'yaml':
        try:
            data = yaml.safe_load(content)
            if 'proxies' in data:
                for proxy in data['proxies']:
                    # 从 Clash 配置中提取节点（假设包含完整节点链接）
                    # 如果节点格式不同，可根据实际情况调整
                    node_str = proxy.get('server', '') + ':' + str(proxy.get('port', ''))
                    nodes.add(node_str)
        except yaml.YAMLError as e:
            print(f"YAML 解析失败: {e}")
    else:  # 默认按纯文本处理
        for pattern in node_patterns:
            found_nodes = re.findall(pattern, content)
            nodes.update(found_nodes)

    return list(nodes)

def process_url_for_nodes(url):
    """处理单个 URL，提取节点，支持不同格式"""
    extracted_nodes = set()
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        content = response.text

        # 判断内容类型
        if 'text/plain' in content_type:
            # 检查是否为 base64 编码
            if re.match(r'^[A-Za-z0-9+/=]+$', content.strip()):
                extracted_nodes.update(extract_nodes_from_content(content, 'base64'))
            else:
                extracted_nodes.update(extract_nodes_from_content(content, 'plain'))
        elif 'yaml' in content_type or url.endswith('.yaml'):
            extracted_nodes.update(extract_nodes_from_content(content, 'yaml'))
        else:
            # 处理包含链接的页面
            links = re.findall(r'(https?://[^\s]+)', content)
            for link in links:
                try:
                    node_response = requests.get(link, timeout=5)
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
    except requests.exceptions.RequestException as e:
        print(f"无法访问或解析 {url}: {e}")
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
        "https://github.com/qjlxg/TV/raw/refs/heads/main/url/igdux.top.txt",          # 包含链接
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",       # 直接节点（纯文本）
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt",    # base64 格式
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/clash.yaml",   # Clash 格式
    ]

    all_extracted_nodes = set()
    for url in main_urls:
        print(f"正在处理 URL: {url}")
        nodes_from_url = process_url_for_nodes(url)
        all_extracted_nodes.update(nodes_from_url)

    unique_nodes = sorted(list(all_extracted_nodes))
    print(f"共提取到 {len(all_extracted_nodes)} 个节点，{len(unique_nodes)} 个唯一节点。")
    save_nodes_to_file(unique_nodes)
