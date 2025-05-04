import base64
import requests
import yaml
import os
import re

# 全局计数器用于 bing 命名
bing_counter = 0

def fetch_data(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"无法从 {url} 获取数据: {e}")
        return None

def decode_base64(data):
    try:
        return base64.b64decode(data + '=' * (-len(data) % 4)).decode('utf-8')
    except Exception:
        return data

def parse_yaml(data):
    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as e:
        print(f"YAML 解析错误: {e}")
        return None

def extract_proxies(data):
    yaml_data = parse_yaml(data)
    if yaml_data and isinstance(yaml_data, dict) and 'proxies' in yaml_data:
        return yaml_data['proxies']
    return []

def parse_ss(link):
    if not link.startswith('ss://'):
        return None
    try:
        link_body = link[5:]
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        else:
            name = 'ss'
        if '@' in link_body:
            userinfo, serverinfo = link_body.split('@', 1)
            method_password = base64.urlsafe_b64decode(userinfo + '=' * (-len(userinfo) % 4)).decode('utf-8')
            method, password = method_password.split(':', 1)
            server, port = serverinfo.split(':', 1)
        else:
            decoded = base64.urlsafe_b64decode(link_body + '=' * (-len(link_body) % 4)).decode('utf-8')
            method, rest = decoded.split(':', 1)
            password, server_port = rest.rsplit('@', 1)
            server, port = server_port.split(':', 1)
        port = re.split(r'[/\?]', port)[0]
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

def parse_vmess(link):
    if not link.startswith('vmess://'):
        return None
    try:
        vmess_data = base64.urlsafe_b64decode(link.split('://')[1] + '=' * (-len(link.split('://')[1]) % 4)).decode('utf-8')
        vmess_json = yaml.safe_load(vmess_data)
        return {
            'name': vmess_json.get('ps', vmess_json.get('add')),
            'server': vmess_json['add'],
            'port': int(vmess_json['port']),
            'type': 'vmess',
            'uuid': vmess_json['id'],
            'alterId': int(vmess_json.get('aid', 0)),
            'cipher': 'auto',
            'tls': vmess_json.get('tls', False),
            'udp': True
        }
    except Exception as e:
        print(f"解析 vmess:// 链接失败: {e}")
        return None

def parse_trojan(link):
    if not link.startswith('trojan://'):
        return None
    try:
        link_body = link[9:]
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        else:
            name = 'trojan'
        if '@' not in link_body:
            return None
        password, serverinfo = link_body.split('@', 1)
        if ':' not in serverinfo:
            return None
        server, port = serverinfo.split(':', 1)
        port = re.split(r'[/\?]', port)[0]
        return {
            'name': name,
            'server': server,
            'port': int(port),
            'type': 'trojan',
            'password': password,
            'udp': True
        }
    except Exception as e:
        print(f"解析 trojan:// 链接失败: {e}")
        return None

def parse_vless(link):
    if not link.startswith('vless://'):
        return None
    try:
        link_body = link[8:]
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        else:
            name = 'vless'
        if '@' not in link_body:
            return None
        uuid, serverinfo = link_body.split('@', 1)
        if ':' not in serverinfo:
            return None
        server, port = serverinfo.split(':', 1)
        port = re.split(r'[/\?]', port)[0]
        return {
            'name': name,
            'server': server,
            'port': int(port),
            'type': 'vless',
            'uuid': uuid,
            'tls': True,
            'servername': server,
            'udp': True
        }
    except Exception as e:
        print(f"解析 vless:// 链接失败: {e}")
        return None

def parse_hysteria2(link):
    if not link.startswith('hysteria2://'):
        return None
    try:
        link_body = link[11:]
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        else:
            name = 'hysteria2'
        if '@' not in link_body:
            return None
        password, serverinfo = link_body.split('@', 1)
        if ':' not in serverinfo:
            return None
        server, port = serverinfo.split(':', 1)
        port = re.split(r'[/\?]', port)[0]
        return {
            'name': name,
            'server': server,
            'port': int(port),
            'type': 'hysteria2',
            'password': password,
            'udp': True
        }
    except Exception as e:
        print(f"解析 hysteria2:// 链接失败: {e}")
        return None

def extract_flag(name):
    global bing_counter
    bing_counter += 1
    name = str(name)
    match = re.match(r'^([\U0001F1E6-\U0001F1FF]{2})', name)
    if match:
        flag = match.group(1)
        return f"{flag} bing{bing_counter}"
    else:
        return f"bing{bing_counter}"

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

def main(urls):
    global bing_counter
    bing_counter = 0
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
                elif link.startswith('vless://'):
                    proxy = parse_vless(link)
                elif link.startswith('hysteria2://'):
                    proxy = parse_hysteria2(link)
                if proxy:
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
