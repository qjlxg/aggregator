import requests
import re
import os
import base64
import yaml
import json

PROTOCOLS = ['vless://', 'vmess://', 'trojan://', 'ss://', 'ssr://', 'wireguard://', 'grpc://', 'snell://', 'hysteria://', 'hysteria2://', 'tuic://', 'juicity://']

# 插入上述修改后的 extract_nodes_from_content 函数

def process_url_for_nodes(url, retries=3, timeout=10):
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
