import requests
import re
import os
import base64
import yaml
import json
import urllib.parse

# 定义支持的节点协议
PROTOCOLS = [
    'vless://', 'vmess://', 'trojan://', 'ss://', 'ssr://',
    'wireguard://', 'grpc://', 'snell://', 'hysteria://',
    'hysteria2://', 'tuic://', 'juicity://'
]

def standardize_node(node):
    """标准化节点字符串以确保去重一致性"""
    if not any(node.startswith(proto) for proto in PROTOCOLS):
        return node
    
    # 分割名称部分
    config_part, *name_part = node.split('#', 1)
    name = name_part[0] if name_part else 'unnamed'
    
    # 标准化配置部分
    config_part = config_part.strip().lower()  # 统一小写并去除多余空格
    if '?' in config_part:  # 处理带参数的协议（如 VLESS、Trojan）
        base, params = config_part.split('?', 1)
        param_list = params.split('&')
        param_list.sort()  # 参数排序
        config_part = f"{base}?{'&'.join(param_list)}"
    
    # 重新组合，保留原始名称
    return f"{config_part}#{name}"

def get_node_key(node):
    """提取节点的唯一标识，用于基于关键信息的去重"""
    try:
        if node.startswith('vmess://'):
            encoded_part = node.split('://')[1].split('#')[0]  # 移除名称部分
            decoded = base64.urlsafe_b64decode(encoded_part + '=' * (4 - len(encoded_part) % 4)).decode('utf-8')
            vmess_dict = json.loads(decoded)
            return ('vmess', vmess_dict['add'], vmess_dict['port'], vmess_dict['id'])
        elif node.startswith('vless://'):
            parsed = urllib.parse.urlparse(node.split('#')[0])
            return ('vless', parsed.hostname, parsed.port, parsed.username)
        elif node.startswith('trojan://'):
            parsed = urllib.parse.urlparse(node.split('#')[0])
            return ('trojan', parsed.hostname, parsed.port, parsed.username)
        elif node.startswith('ss://'):
            parsed = urllib.parse.urlparse(node.split('#')[0])
            auth_str = base64.urlsafe_b64decode(parsed.username + '=' * (4 - len(parsed.username) % 4)).decode('utf-8')
            method, password = auth_str.split(':', 1)
            return ('ss', parsed.hostname, parsed.port, method, password)
        else:
            return node  # 对于无法解析的协议，退回原始字符串
    except Exception:
        return node  # 解析失败时使用原始字符串

def rename_node(node, index):
    """重命名节点为 yandex + 数字"""
    if '#' in node:
        config_part, _ = node.split('#', 1)
        new_name = f"yandex{index}"
        return f"{config_part}#{new_name}"
    else:
        return f"{node}#yandex{index}"  # 如果没有名称部分，添加新名称

def extract_nodes_from_content(content, content_type='plain', source_url="Unknown"):
    """根据内容类型提取节点信息，并进行标准化"""
    nodes = set()
    if not content:
        print(f"DEBUG: [{source_url}] 内容为空，无法提取节点 (类型: {content_type})")
        return list(nodes)

    if content_type == 'base64':
        try:
            missing_padding = len(content) % 4
            if missing_padding:
                content += '=' * (4 - missing_padding)
            decoded_content = base64.b64decode(content).decode('utf-8', errors='ignore')
            for line in decoded_content.splitlines():
                line = line.strip()
                if any(line.startswith(proto) for proto in PROTOCOLS):
                    nodes.add(standardize_node(line))
            print(f"DEBUG: [{source_url}] Base64解码后提取到 {len(nodes)} 个节点")
        except Exception as e:
            print(f"错误: [{source_url}] Base64解码失败: {e}. 原始内容前100字符: {content[:100]}")
    elif content_type == 'yaml':
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and 'proxies' in data and isinstance(data['proxies'], list):
                print(f"DEBUG: [{source_url}] YAML解析到 {len(data['proxies'])} 个代理")
                for i, proxy in enumerate(data['proxies']):
                    if not isinstance(proxy, dict):
                        print(f"警告: [{source_url}] YAML proxies列表中第 {i+1} 项不是字典格式, 跳过。")
                        continue
                    node_type = proxy.get('type')
                    try:
                        if node_type == 'vmess':
                            vmess_dict = {
                                "v": "2", "ps": proxy.get('name', 'unnamed'), "add": proxy.get('server'),
                                "port": proxy.get('port'), "id": proxy.get('uuid'), "aid": proxy.get('alterId', 0),
                                "scy": proxy.get('cipher', 'auto'), "net": proxy.get('network', 'tcp'),
                                "type": proxy.get('headerType', 'none'),
                                "host": proxy.get('host', proxy.get('ws-opts', {}).get('headers', {}).get('Host', '')),
                                "path": proxy.get('path', proxy.get('ws-opts', {}).get('path', '')),
                                "tls": "tls" if proxy.get('tls') else ""
                            }
                            if not all([vmess_dict["add"], vmess_dict["port"], vmess_dict["id"]]):
                                print(f"警告: [{source_url}] Vmess代理缺少必要字段: {proxy.get('name')}")
                                continue
                            vmess_str = json.dumps(vmess_dict, sort_keys=True)
                            node_str = f"vmess://{base64.urlsafe_b64encode(vmess_str.encode()).decode().rstrip('=')}"
                            nodes.add(standardize_node(node_str))
                        elif node_type == 'vless':
                            uuid = proxy.get('uuid')
                            server = proxy.get('server')
                            port = proxy.get('port')
                            if not all([uuid, server, port]):
                                print(f"警告: [{source_url}] Vless代理缺少必要字段: {proxy.get('name')}")
                                continue
                            params = {
                                "encryption": proxy.get('encryption', 'none'),
                                "security": 'tls' if proxy.get('tls') else 'none',
                                "sni": proxy.get('sni', proxy.get('serverName', '')),
                                "fp": proxy.get('fingerprint', proxy.get('client-fingerprint', '')),
                                "type": proxy.get('network', 'tcp'),
                                "host": proxy.get('host', proxy.get('ws-opts', {}).get('headers', {}).get('Host', '')),
                                "path": proxy.get('path', proxy.get('ws-opts', {}).get('path', '')),
                                "flow": proxy.get('flow', '')
                            }
                            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items()) if v])
                            node_str = f"vless://{uuid}@{server}:{port}?{query_string}#{proxy.get('name', 'unnamed')}"
                            nodes.add(standardize_node(node_str))
                        elif node_type == 'trojan':
                            password = proxy.get('password')
                            server = proxy.get('server')
                            port = proxy.get('port')
                            if not all([password, server, port]):
                                print(f"警告: [{source_url}] Trojan代理缺少必要字段: {proxy.get('name')}")
                                continue
                            params = {
                                "sni": proxy.get('sni', proxy.get('serverName', '')),
                                "security": 'tls' if proxy.get('tls', True) else 'none',
                            }
                            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items()) if v])
                            node_str = f"trojan://{password}@{server}:{port}?{query_string}#{proxy.get('name', 'unnamed')}"
                            nodes.add(standardize_node(node_str))
                        elif node_type == 'ss':
                            method = proxy.get('cipher')
                            password = proxy.get('password')
                            server = proxy.get('server')
                            port = proxy.get('port')
                            if not all([method, password, server, port]):
                                print(f"警告: [{source_url}] SS代理缺少必要字段: {proxy.get('name')}")
                                continue
                            auth_str = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip('=')
                            node_str = f"ss://{auth_str}@{server}:{port}#{proxy.get('name', 'unnamed')}"
                            nodes.add(standardize_node(node_str))
                        elif node_type == 'hysteria2':
                            auth = proxy.get('auth', proxy.get('password'))
                            server = proxy.get('server')
                            port = proxy.get('port')
                            if not all([auth, server, port]):
                                print(f"警告: [{source_url}] Hysteria2代理缺少必要字段: {proxy.get('name')}")
                                continue
                            params = {
                                "sni": proxy.get('sni', proxy.get('serverName', '')),
                                "insecure": '1' if proxy.get('skip-cert-verify', False) else '',
                            }
                            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items()) if v])
                            node_str = f"hysteria2://{auth}@{server}:{port}?{query_string}#{proxy.get('name', 'unnamed')}"
                            nodes.add(standardize_node(node_str))
                    except Exception as e_proxy:
                        print(f"错误: [{source_url}] 处理YAML代理 {proxy.get('name', 'N/A')} 失败: {e_proxy}")
            else:
                print(f"DEBUG: [{source_url}] YAML文件格式不正确。Data type: {type(data)}")
        except yaml.YAMLError as e_yaml:
            print(f"错误: [{source_url}] YAML解析失败: {e_yaml}")
    else:  # 默认按纯文本处理
        for line in content.splitlines():
            line = line.strip()
            if any(line.startswith(proto) for proto in PROTOCOLS):
                nodes.add(standardize_node(line))
    return list(nodes)

def fetch_and_extract_nodes(url, retries=3, timeout=25, is_sub_link=False):
    """获取URL内容并提取节点，处理不同内容类型和子链接"""
    print(f"INFO: 开始处理 {'子链接' if is_sub_link else '主URL'}: {url}")
    extracted_nodes_from_this_url = set()

    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            content = response.text
            content_type_header = response.headers.get('Content-Type', '').lower()
            print(f"DEBUG: [{url}] 状态码: {response.status_code}, Content-Type: {content_type_header}")

            if url.endswith(('.yaml', '.yml')) or 'yaml' in content_type_header:
                print(f"INFO: [{url}] 判断为YAML")
                extracted_nodes_from_this_url.update(extract_nodes_from_content(content, 'yaml', source_url=url))
            elif 'text/plain' in content_type_header and re.fullmatch(r'[A-Za-z0-9+/=\s\r\n]+', content.strip()) and len(content.strip()) > 20:
                is_likely_base64 = False
                try:
                    sample_decoded = base64.b64decode(content.strip().splitlines()[0][:200]).decode('utf-8', errors='ignore')
                    if any(proto in sample_decoded for proto in PROTOCOLS):
                        is_likely_base64 = True
                except:
                    pass
                if is_likely_base64:
                    print(f"INFO: [{url}] 判断为Base64编码文本")
                    extracted_nodes_from_this_url.update(extract_nodes_from_content(content.strip(), 'base64', source_url=url))
                else:
                    print(f"INFO: [{url}] 判断为普通文本")
                    extracted_nodes_from_this_url.update(extract_nodes_from_content(content, 'plain', source_url=url))
            elif 'text/plain' in content_type_header:
                print(f"INFO: [{url}] 判断为普通文本")
                extracted_nodes_from_this_url.update(extract_nodes_from_content(content, 'plain', source_url=url))

            if not extracted_nodes_from_this_url and not url.endswith(('.yaml', '.yml')):
                print(f"INFO: [{url}] 未直接提取到节点，尝试作为链接列表解析")
                potential_links = re.findall(r'https?://[^\s\'"<>]+', content)
                links = list(set(potential_links))
                if links:
                    print(f"INFO: [{url}] 提取到 {len(links)} 个潜在子链接")
                    for i, link in enumerate(links):
                        if "github.com" in link and not ("raw.githubusercontent.com" in link or "/raw/" in link):
                            print(f"DEBUG: [{url}] 跳过非raw GitHub链接: {link}")
                            continue
                        if link.lower().endswith(('.png', '.jpg', '.gif', '.zip', '.exe', '.pdf', '.md')):
                            print(f"DEBUG: [{url}] 跳过非订阅文件类型: {link}")
                            continue
                        print(f"INFO: [{url}] 处理子链接 {i+1}/{len(links)}: {link}")
                        extracted_nodes_from_this_url.update(fetch_and_extract_nodes(link, retries, timeout, is_sub_link=True))
            break
        except requests.exceptions.RequestException as e:
            print(f"错误: [{url}] 尝试 {attempt+1}/{retries} 失败: {e}")
            if attempt == retries - 1:
                print(f"错误: [{url}] 所有重试均失败")
    
    if extracted_nodes_from_this_url:
        print(f"成功: 从 {url} 共提取到 {len(extracted_nodes_from_this_url)} 个节点")
    return list(extracted_nodes_from_this_url)

def save_nodes_to_file(nodes, filename="data/ji.txt"):
    """将节点保存到文件，每行一个节点"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        for node in nodes:
            f.write(node + "\n")
    print(f"文件: 成功保存 {len(nodes)} 个唯一节点到 {filename}")

if __name__ == "__main__":
    main_urls = [
        "https://github.com/qjlxg/TV/raw/refs/heads/main/url/igdux.top.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/clash.yaml",
    ]

    all_extracted_nodes = set()
    for url in main_urls:
        nodes_from_url = fetch_and_extract_nodes(url)
        if nodes_from_url:
            all_extracted_nodes.update(nodes_from_url)

    # 基于关键信息进行最终去重
    unique_nodes = {}
    for node in all_extracted_nodes:
        key = get_node_key(node)
        if key not in unique_nodes:
            unique_nodes[key] = node

    # 对去重后的节点进行重命名
    renamed_nodes = []
    for index, (key, node) in enumerate(unique_nodes.items(), start=1):
        renamed_node = rename_node(node, index)
        renamed_nodes.append(renamed_node)

    # 排序并保存
    unique_nodes_list = sorted(renamed_nodes)
    print(f"\n总结: 共提取到 {len(all_extracted_nodes)} 个节点，去重后 {len(unique_nodes_list)} 个唯一节点。")
    save_nodes_to_file(unique_nodes_list)
