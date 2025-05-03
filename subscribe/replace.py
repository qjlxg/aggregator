import base64
import requests
import yaml
import os
import re
import json

bing_counter = 0

def fetch_data(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"已获取 {url}，长度: {len(response.text)}")
        return response.text
    except requests.RequestException as e:
        print(f"无法从 {url} 获取数据: {e}")
        return None

def decode_base64_if_needed(data):
    if any(proto in data for proto in ['vmess://', 'ss://', 'trojan://', 'vless://', 'hysteria2://', 'tuic://', 'hysteria://', 'hy2://']):
        print("检测到明文节点格式，直接返回")
        return data
    try:
        decoded = base64.b64decode(data).decode('utf-8', errors='ignore')
        print(f"Base64解码成功，长度: {len(decoded)}")
        return decoded
    except Exception:
        print("Base64解码失败，直接返回原文")
        return data

def parse_yaml(data):
    try:
        result = yaml.safe_load(data)
        print("YAML解析成功")
        return result
    except yaml.YAMLError as e:
        print(f"YAML 解析错误: {e}")
        return None

def extract_proxies(data):
    if data.lstrip().startswith('proxies:'):
        yaml_data = parse_yaml(data)
        if yaml_data and isinstance(yaml_data, dict) and 'proxies' in yaml_data:
            print(f"YAML中proxies数量: {len(yaml_data['proxies'])}")
            return yaml_data['proxies']
    return []

def extract_port(port_str):
    match = re.match(r'^(\d+)', port_str)
    if match:
        return int(match.group(1))
    raise ValueError(f"无效端口: {port_str}")

def parse_ss(link):
    if link.startswith('ss://'):
        try:
            body = link[5:]
            if '@' not in body:
                # ss://base64?plugin=xxx#name
                base64_part = body.split('#')[0].split('?')[0]
                decoded = base64.urlsafe_b64decode(base64_part + '=' * (-len(base64_part) % 4)).decode('utf-8', errors='ignore')
                if '@' in decoded:
                    method, rest = decoded.split(':', 1)
                    password, server_port = rest.rsplit('@', 1)
                    server, port = server_port.split(':')
                else:
                    print("ss:// base64解码后格式不对，跳过")
                    return None
                name = link.split('#')[1] if '#' in link else server
            else:
                parts = body.split('@')
                method_password = base64.urlsafe_b64decode(parts[0] + '=' * (-len(parts[0]) % 4)).decode('utf-8', errors='ignore')
                method, password = method_password.split(':', 1)
                server_port = parts[1].split('#')
                server, port = server_port[0].split(':')
                name = server_port[1] if len(server_port) > 1 else server
            port = extract_port(port)
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'ss',
                'cipher': method,
                'password': password,
                'udp': True
            }
        except Exception as e:
            print(f"解析 ss:// 链接失败: {e}")
    return None

def parse_vmess(link):
    if link.startswith('vmess://'):
        try:
            raw = link.split('://')[1]
            raw += '=' * (-len(raw) % 4)
            vmess_data = base64.urlsafe_b64decode(raw)
            try:
                vmess_json = json.loads(vmess_data.decode('utf-8', errors='ignore'))
            except Exception:
                print("vmess base64解码后不是合法json或utf-8，跳过")
                return None
            return {
                'name': vmess_json.get('ps', vmess_json.get('add')),
                'server': vmess_json['add'],
                'port': extract_port(str(vmess_json['port'])),
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
    if link.startswith('trojan://'):
        try:
            parts = link.split('://')[1].split('@')
            password = parts[0]
            server_port = parts[1].split('?')[0].split(':')
            server = server_port[0]
            port = extract_port(server_port[1])
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

def parse_hysteria2(link):
    if link.startswith('hysteria2://'):
        try:
            parts = link.split('://')[1].split('@')
            password = parts[0]
            server_port = parts[1].split('?')[0].split(':')
            server = server_port[0]
            port = extract_port(server_port[1])
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

def parse_vless(link):
    if link.startswith('vless://'):
        try:
            parts = link.split('://')[1].split('@')
            uuid = parts[0]
            server_port_params = parts[1].split('?')
            server_port = server_port_params[0].split(':')
            server = server_port[0]
            port = extract_port(server_port[1])
            params = server_port_params[1].split('#')[0] if len(server_port_params) > 1 else ''
            name = link.split('#')[1] if '#' in link else server
            param_dict = {}
            if params:
                for param in params.split('&'):
                    k, v = param.split('=') if '=' in param else (param, '')
                    param_dict[k] = v
            security = param_dict.get('security', 'none')
            type_ = param_dict.get('type', 'tcp')
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'vless',
                'uuid': uuid,
                'tls': security == 'tls',
                'network': type_,
                'udp': True
            }
        except Exception as e:
            print(f"解析 vless:// 链接失败: {e}")
    return None

def parse_tuic(link):
    if link.startswith('tuic://'):
        try:
            parts = link.split('://')[1].split('@')
            uuid_password = parts[0].split(':')
            uuid = uuid_password[0]
            password = uuid_password[1] if len(uuid_password) > 1 else ''
            server_port_params = parts[1].split('?')
            server_port = server_port_params[0].split(':')
            server = server_port[0]
            port = extract_port(server_port[1])
            params = server_port_params[1].split('#')[0] if len(server_port_params) > 1 else ''
            name = link.split('#')[1] if '#' in link else server
            param_dict = {}
            if params:
                for param in params.split('&'):
                    k, v = param.split('=') if '=' in param else (param, '')
                    param_dict[k] = v
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'tuic',
                'uuid': uuid,
                'password': password,
                'udp': True
            }
        except Exception as e:
            print(f"解析 tuic:// 链接失败: {e}")
    return None

def parse_hysteria(link):
    if link.startswith('hysteria://'):
        try:
            parts = link.split('://')[1].split('?')
            server_port = parts[0].split(':')
            server = server_port[0]
            port = extract_port(server_port[1])
            params = parts[1].split('#')[0] if len(parts) > 1 else ''
            name = link.split('#')[1] if '#' in link else server
            param_dict = {}
            if params:
                for param in params.split('&'):
                    k, v = param.split('=') if '=' in param else (param, '')
                    param_dict[k] = v
            auth = param_dict.get('auth', '')
            upmbps = param_dict.get('upmbps', 10)
            downmbps = param_dict.get('downmbps', 50)
            return {
                'name': name,
                'server': server,
                'port': port,
                'type': 'hysteria',
                'auth_str': auth,
                'up_mbps': int(upmbps),
                'down_mbps': int(downmbps),
                'udp': True
            }
        except Exception as e:
            print(f"解析 hysteria:// 链接失败: {e}")
    return None

def parse_hy2(link):
    if link.startswith('hy2://'):
        return parse_hysteria2(link.replace('hy2://', 'hysteria2://'))
    return None

def extract_flag(name):
    global bing_counter
    bing_counter += 1
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
                nested_str = ', '.join([f"{k}: '{v}'" if isinstance(v, str) else f"{k}: {v}" for k, v in value.items()])
                items.append(f"{key}: {{{nested_str}}}")
            else:
                items.append(f"{key}: '{value}'" if isinstance(value, str) else f"{key}: {value}")
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
        print(f"正在处理URL: {url}")
        raw_data = fetch_data(url)
        print(f"获取到原始数据长度: {len(raw_data) if raw_data else 0}")
        if raw_data is None:
            continue

        decoded_data = decode_base64_if_needed(raw_data)
        print(f"解码后数据长度: {len(decoded_data) if decoded_data else 0}")
        yaml_proxies = extract_proxies(decoded_data)
        print(f"YAML解析得到节点数: {len(yaml_proxies) if yaml_proxies else 0}")
        
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
            print(f"逐行处理节点链接，行数: {len(links)}")
            for link in links:
                link = link.strip()
                if not link or link.startswith('#') or ':' not in link:
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
                elif link.startswith('vless://'):
                    proxy = parse_vless(link)
                elif link.startswith('tuic://'):
                    proxy = parse_tuic(link)
                elif link.startswith('hysteria://'):
                    proxy = parse_hysteria(link)
                elif link.startswith('hy2://'):
                    proxy = parse_hy2(link)
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
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/base64.txt',
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/all_clash.txt',
    ]
    main(urls)
