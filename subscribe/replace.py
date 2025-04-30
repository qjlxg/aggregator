import base64
import requests
import yaml
import os
import re

# 全局计数器用于 bing 命名
bing_counter = 0

# 从 URL 获取数据的函数
def fetch_data(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"无法从 {url} 获取数据: {e}")
        return None

# 解码 Base64 数据的函数
def decode_base64(data):
    try:
        return base64.b64decode(data).decode('utf-8')
    except Exception:
        return data

# 解析 YAML 数据的函数
def parse_yaml(data):
    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as e:
        print(f"YAML 解析错误: {e}")
        return None

# 从数据中提取代理配置的函数
def extract_proxies(data):
    yaml_data = parse_yaml(data)
    if yaml_data and isinstance(yaml_data, dict) and 'proxies' in yaml_data:
        return yaml_data['proxies']
    return []

# 处理 server 字段：移除中文字符，替换域名
def process_server(server):
    # 移除中文字符（Unicode 范围 \u4e00-\u9fff）
    server = re.sub(r'[\u4e00-\u9fff]', '', server)
    # 判断是否为 IP 地址
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', server):
        return server  # 如果是 IP 地址，保持不变
    else:
        return 'yandex'  # 如果是域名，替换为 "yandex"

# 解析 ss:// 链接
def parse_ss(link):
    if link.startswith('ss://'):
        try:
            parts = link.split('://')[1].split('@')
            method_password = base64.urlsafe_b64decode(parts[0] + '=' * (-len(parts[0]) % 4)).decode('utf-8')
            method, password = method_password.split(':')
            server_port = parts[1].split('#')
            server, port = server_port[0].split(':')
            name = server_port[1] if len(server_port) > 1 else server
            return {
                'name': name,
                'server': server,
                'port': int(port),
                'type': 'ss',
                'cipher': method,
                'password': password,
                'udp': True
            }
        except Exception as e:
            print(f"解析 ss:// 链接失败: {e}")
    return None

# 解析 vmess:// 链接
def parse_vmess(link):
    if link.startswith('vmess://'):
        try:
            vmess_data = base64.urlsafe_b64decode(link.split('://')[1] + '=' * (-len(link.split('://')[1]) % 4)).decode('utf-8')
            vmess_json = yaml.safe_load(vmess_data)
            return {
                'name': vmess_json.get('ps', vmess_json.get('add')),
                'server': vmess_json['add'],
                'port': int(vmess_json['port']),
                'type': 'vmess',
                'uuid': vmess_json['id'],
                'alterId': int(vmess_json['aid']),
                'cipher': 'auto',
                'tls': vmess_json.get('tls', False),
                'udp': True
            }
        except Exception as e:
            print(f"解析 vmess:// 链接失败: {e}")
    return None

# 解析 trojan:// 链接
def parse_trojan(link):
    if link.startswith('trojan://'):
        try:
            parts = link.split('://')[1].split('@')
            password = parts[0]
            server_port = parts[1].split('?')[0].split(':')
            server = server_port[0]
            port = int(server_port[1])
            name = link.split('#')[1] if '#' in link else server
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'trojan',
                'password': password,
                'udp': True
            }
        except Exception as e:
            print(f"解析 trojan:// 链接失败: {e}")
    return None

# 解析 hysteria2:// 链接
def parse_hysteria2(link):
    if link.startswith('hysteria2://'):
        try:
            parts = link.split('://')[1].split('@')
            password = parts[0]
            server_port = parts[1].split('?')[0].split(':')
            server = server_port[0]
            port = int(server_port[1])
            name = link.split('#')[1] if '#' in link else server
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'hysteria2',
                'password': password,
                'udp': True
            }
        except Exception as e:
            print(f"解析 hysteria2:// 链接失败: {e}")
    return None

# 提取国旗符号并添加空格，或使用 bing 命名
def extract_flag(name):
    global bing_counter
    match = re.match(r'^[🇦-🇿]{2}', name)
    if match:
        return match.group(0) + ' ' + name[2:]  # 保留国旗后的名称并加空格
    bing_counter += 1
    return f"bing{bing_counter} "  # 没有国旗时使用 bing 命名并加空格

# 生成符合指定格式的 YAML 字符串
def generate_yaml(proxies):
    yaml_str = "proxies:\n"
    for proxy in proxies:
        proxy_str = ' - {'
        items = []
        for key, value in proxy.items():
            if isinstance(value, dict):
                nested_str = ', '.join([f"{k}: {repr(v)}" if isinstance(v, str) else f"{k}: {v}" for k, v in value.items()])
                items.append(f"{key}: {{{nested_str}}}")
            else:
                items.append(f"{key}: {repr(value)}" if isinstance(value, str) else f"{key}: {value}")
        proxy_str += ', '.join(items)
        proxy_str += '}\n'
        yaml_str += proxy_str
    return yaml_str

# 主函数
def main(urls):
    global bing_counter
    bing_counter = 0  # 重置计数器
    all_proxies = []
    seen = set()

    for url in urls:
        raw_data = fetch_data(url)
        if raw_data is None:
            continue

        decoded_data = decode_base64(raw_data)
        yaml_proxies = extract_proxies(decoded_data)
        
        if yaml_proxies:
            for proxy in yaml_proxies:
                if not isinstance(proxy, dict) or 'server' not in proxy or 'port' not in proxy:
                    continue
                # 处理 server 字段
                proxy['server'] = process_server(proxy['server'])
                identifier = (proxy['server'], proxy['port'])
                if identifier not in seen:
                    seen.add(identifier)
                    proxy['name'] = extract_flag(proxy['name'])
                    all_proxies.append(proxy)
        else:
            links = decoded_data.splitlines()
            for link in links:
                link = link.strip()
                if not link:
                    continue
                proxy = None
                if link.startswith('ss://'):
                    proxy = parse_ss(link)
                elif link.startswith('vmess://'):
                    proxy = parse_vmess(link)
                elif link.startswith('trojan://'):
                    proxy = parse_trojan(link)
                elif link.startswith('hysteria2://'):
                    proxy = parse_hysteria2(link)
                if proxy:
                    # 处理 server 字段
                    proxy['server'] = process_server(proxy['server'])
                    identifier = (proxy['server'], proxy['port'])
                    if identifier not in seen:
                        seen.add(identifier)
                        proxy['name'] = extract_flag(proxy['name'])
                        all_proxies.append(proxy)

    if not all_proxies:
        print("未找到有效的代理配置！")
        return

    os.makedirs('data', exist_ok=True)
    yaml_content = generate_yaml(all_proxies)
    output_path = 'data/clash.yaml'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    print(f"Clash 配置文件已保存到 {output_path}")

# 示例运行
if __name__ == "__main__":
    urls = [
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/clash.yaml',
        'https://github.com/qjlxg/license/raw/refs/heads/main/all_clash.txt',
        'https://github.com/qjlxg/license/raw/refs/heads/main/base64.txt',
        'https://github.com/qjlxg/license/raw/refs/heads/main/Long_term_subscription_num',
        'https://github.com/qjlxg/license/raw/refs/heads/main/data/clash.yaml',
        'https://raw.githubusercontent.com/qjlxg/license/refs/heads/main/data/transporter.txt',
        'https://raw.githubusercontent.com/qjlxg/cheemsar/refs/heads/main/Long_term_subscription_num',
        'https://raw.githubusercontent.com/qjlxg/cheemsar-2/refs/heads/main/Long_term_subscription_num',
    ]
    main(urls)
