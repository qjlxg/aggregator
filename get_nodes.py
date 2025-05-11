import requests
import re
import os

def extract_links_from_url(url):
    """从 URL 的内容中提取链接。"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'text/plain' in content_type:
            # 如果是纯文本文件，直接返回 URL 本身，作为待处理的“链接”
            return [url]
        else:
            return re.findall(r'(https?://[^\s]+)', response.text)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching or parsing {url}: {e}")
        return []

def extract_nodes_from_content(content):
    """从文本内容中提取可能的节点信息。"""
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
    for pattern in node_patterns:
        found_nodes = re.findall(pattern, content)
        nodes.update(found_nodes)
    return list(nodes)

def process_url_for_nodes(url):
    """处理单个 URL，判断是链接列表还是直接包含节点。"""
    extracted_nodes = set()
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'text/plain' in content_type:
            # 直接读取文本内容并提取节点
            extracted_nodes.update(extract_nodes_from_content(response.text))
        else:
            # 提取链接，并从这些链接的内容中提取节点
            links = re.findall(r'(https?://[^\s]+)', response.text)
            for link in links:
                try:
                    node_response = requests.get(link, timeout=5)
                    node_response.raise_for_status()
                    extracted_nodes.update(extract_nodes_from_content(node_response.text))
                except requests.exceptions.RequestException:
                    # 忽略无法访问的链接
                    pass
    except requests.exceptions.RequestException as e:
        print(f"Error fetching or parsing {url}: {e}")
    return list(extracted_nodes)

def save_nodes_to_file(nodes, filename="data/ji.txt"):
    """将节点列表保存到文件中，每个节点一行。"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        for node in sorted(list(nodes)):
            f.write(node + "\n")
    print(f"Successfully saved {len(nodes)} unique nodes to {filename}")

if __name__ == "__main__":
    main_urls = [
        "https://github.com/qjlxg/TV/raw/refs/heads/main/url/igdux.top.txt",
        "https://github.com/qjlxg/TV/raw/refs/heads/main/ss.txt",  # 直接包含节点的链接
        # 在这里添加更多你想要读取的 URL
    ]

    all_extracted_nodes = set()
    for url in main_urls:
        print(f"Processing URL: {url}")
        nodes_from_url = process_url_for_nodes(url)
        all_extracted_nodes.update(nodes_from_url)

    unique_nodes = sorted(list(all_extracted_nodes))
    print(f"Extracted {len(all_extracted_nodes)} nodes, {len(unique_nodes)} unique nodes in total.")

    save_nodes_to_file(unique_nodes)
