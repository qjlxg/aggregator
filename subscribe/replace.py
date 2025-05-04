import base64
import requests
import yaml
import os
import re

bing_counter = 0
vmess_errors = set()

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

def extract_host_port(server_port):
    m = re.match(r'^\[?([0-9a-fA-F:.]+)\]?:([0-9]+)$', server_port)
    if m:
        return m.group(1), int(m.group(2))
    parts = server_port.rsplit(':', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return server_port, None

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
            server, port = extract_host_port(serverinfo)
        else:
            decoded = base64.urlsafe_b64decode(link_body + '=' * (-len(link_body) % 4)).decode('utf-8')
            method, rest = decoded.split(':', 1)
            password, server_port = rest.rsplit('@', 1)
            server, port = extract_host_port(server_port)
        if port is None:
            return None
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
    if not link.startswith('vmess://'):
        return None
    try:
        b64 = link[8:]
        b64 = re.sub(r'[^A-Za-z0-9+/=]', '', b64)
        b64 += '=' * (-len(b64) % 4)
        try:
            raw = base64.b64decode(b64)
        except Exception as e:
            err = f"base64解码错误: {e}"
            if err not in vmess_errors:
                print(f"解析 vmess:// 链接失败: {err}")
                vmess_errors.add(err)
            return None
        try:
            vmess_data = raw.decode('utf-8')
        except Exception as e:
            err = f"utf-8解码错误: {e}"
            if err not in vmess_errors:
                print(f"解析 vmess:// 链接失败: {err}")
                vmess_errors.add(err)
            return None
        try:
            vmess_json = yaml.safe_load(vmess_data)
        except Exception as e:
            err = f"JSON解析错误: {e}"
            if err not in vmess_errors:
                print(f"解析 vmess:// 链接失败: {err}")
                vmess_errors.add(err)
            return None
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
        err = f"{e}"
        if err not in vmess_errors:
            print(f"解析 vmess:// 链接失败: {err}")
            vmess_errors.add(err)
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
        server, port = extract_host_port(serverinfo.split('?', 1)[0].split('/', 1)[0])
        if port is None:
            return None
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
        server, port = extract_host_port(serverinfo.split('?', 1)[0].split('/', 1)[0])
        if port is None:
            return None
        return {
            'name': name,
            'server': server,
            'port': port,
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
        server, port = extract_host_port(serverinfo.split('?', 1)[0].split('/', 1)[0])
        if port is None:
            return None
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
        lines = decoded_data.splitlines()
        for line in lines:
            line = line.strip()
            if not line or not any(line.startswith(s) for s in ['ss://','vmess://','trojan://','vless://','hysteria2://','proxies:']):
                continue
            proxy = None
            if line.startswith('ss://'):
                proxy = parse_ss(line)
            elif line.startswith('vmess://'):
                proxy = parse_vmess(line)
            elif line.startswith('trojan://'):
                proxy = parse_trojan(line)
            elif line.startswith('vless://'):
                proxy = parse_vless(line)
            elif line.startswith('hysteria2://'):
                proxy = parse_hysteria2(line)
            elif line.startswith('proxies:'):
                try:
                    yaml_data = yaml.safe_load('\n'.join(lines))
                    if isinstance(yaml_data, dict) and 'proxies' in yaml_data:
                        for proxy_item in yaml_data['proxies']:
                            if not isinstance(proxy_item, dict) or 'server' not in proxy_item or 'port' not in proxy_item:
                                continue
                            identifier = (proxy_item['server'], proxy_item['port'])
                            if identifier not in seen:
                                seen.add(identifier)
                                proxy_item['name'] = extract_flag(proxy_item['name'])
                                all_proxies.append(proxy_item)
                        break
                except Exception as e:
                    print(f"YAML 解析错误: {e}")
                    break
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
        'https://raw.githubusercontent.com/qjlxg/aggregator/refs/heads/main/data/clash.yaml',
        'https://raw.githubusercontent.com/qjlxg/hy2/refs/heads/main/configtg.txt',
      
       # 'https://github.com/qjlxg/license/raw/refs/heads/main/base64.txt',
      #  'https://github.com/qjlxg/license/raw/refs/heads/main/Long_term_subscription_num',
       # 'https://github.com/qjlxg/license/raw/refs/heads/main/data/clash.yaml',
       # 'https://raw.githubusercontent.com/qjlxg/license/refs/heads/main/data/transporter.txt',
       # 'https://raw.githubusercontent.com/qjlxg/cheemsar/refs/heads/main/Long_term_subscription_num',
       # 'https://raw.githubusercontent.com/qjlxg/cheemsar-2/refs/heads/main/Long_term_subscription_num',
    ]
    main(urls)
