import base64
import requests
import yaml
import os
import re
from datetime import datetime

bing_counter = 0
vmess_errors = set()

def fetch_data(url):
    """从给定的URL获取数据。"""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"无法从 {url} 获取数据: {e}")
        return None

def decode_base64(data):
    """解码Base64编码的数据，同时处理URL安全编码和填充。"""
    try:
        # 移除任何非Base64字符，然后添加正确的填充
        cleaned_data = re.sub(r'[^A-Za-z0-9+/=]', '', data)
        return base64.b64decode(cleaned_data + '=' * (-len(cleaned_data) % 4)).decode('utf-8')
    except Exception:
        return data

def extract_host_port(server_port):
    """从'host:port'字符串中提取主机和端口。"""
    m = re.match(r'^\[?([0-9a-fA-F:.]+)\]?:([0-9]+)$', server_port)
    if m:
        return m.group(1), int(m.group(2))
    parts = server_port.rsplit(':', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return server_port, None

def parse_ss(link):
    """解析Shadowsocks (ss://) 链接。"""
    if not link.startswith('ss://'):
        return None
    try:
        link_body = link[5:]
        name = 'ss'
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)

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
    """解析VMess (vmess://) 链接。"""
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

        # 确保所有必需的键都存在
        if not all(k in vmess_json for k in ['add', 'port', 'id']):
            err = "VMess链接缺少必需的字段 (add, port, id)"
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
    """解析Trojan (trojan://) 链接。"""
    if not link.startswith('trojan://'):
        return None
    try:
        link_body = link[9:]
        name = 'trojan'
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        
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
    """解析VLESS (vless://) 链接。"""
    if not link.startswith('vless://'):
        return None
    try:
        link_body = link[8:]
        name = 'vless'
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        
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
            'tls': True, # VLESS通常假定TLS
            'servername': server, # 通常servername与server相同，除非有特殊配置
            'udp': True
        }
    except Exception as e:
        print(f"解析 vless:// 链接失败: {e}")
        return None

def parse_hysteria2(link):
    """解析Hysteria2 (hysteria2://) 链接。"""
    if not link.startswith('hysteria2://'):
        return None
    try:
        link_body = link[11:]
        name = 'hysteria2'
        if '#' in link_body:
            link_body, name = link_body.split('#', 1)
        
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
    """从代理名称中提取国旗emoji并添加计数器。"""
    global bing_counter
    bing_counter += 1
    name = str(name)
    # 匹配两个连续的Unicode国旗emoji字符
    match = re.match(r'^([\U0001F1E6-\U0001F1FF]{2})', name)
    if match:
        flag = match.group(1)
        return f"{flag} bing{bing_counter}"
    else:
        return f"bing{bing_counter}"

def generate_yaml(proxies):
    """将代理列表生成为Clash代理组的YAML格式字符串。"""
    yaml_str = "proxies:\n"
    for proxy in proxies:
        proxy_str = ' - {'
        items = []
        for key, value in proxy.items():
            if isinstance(value, dict): # 处理嵌套字典，例如Hysteria的obfs
                nested_str = ', '.join([f"{k}: {repr(v)}" if isinstance(v, str) else f"{k}: {v}" for k, v in value.items()])
                items.append(f"{key}: {{{nested_str}}}")
            else:
                items.append(f"{key}: {repr(value)}" if isinstance(value, str) else f"{key}: {value}")
        proxy_str += ', '.join(items)
        proxy_str += '}\n'
        yaml_str += proxy_str
    return yaml_str

def main(urls):
    """主函数，用于获取、解析和保存代理配置。"""
    global bing_counter
    bing_counter = 0 # 每次运行重置计数器
    all_proxies = []
    seen = set() # 用于存储 (server, port) 对，避免重复

    for url in urls:
        print(f"正在从 {url} 获取数据...")
        raw_data = fetch_data(url)
        if raw_data is None:
            continue

        # 尝试解码数据，对于YAML文件，直接尝试加载
        if url.endswith('.yaml'):
            try:
                yaml_data = yaml.safe_load(raw_data)
                if isinstance(yaml_data, dict) and 'proxies' in yaml_data:
                    for proxy_item in yaml_data['proxies']:
                        # 确保代理项是字典且包含必需的键
                        if not isinstance(proxy_item, dict) or 'server' not in proxy_item or 'port' not in proxy_item:
                            continue
                        identifier = (proxy_item['server'], proxy_item['port'])
                        if identifier not in seen:
                            seen.add(identifier)
                            proxy_item['name'] = extract_flag(proxy_item.get('name', 'unknown'))
                            all_proxies.append(proxy_item)
                else:
                    print(f"警告: {url} 不是有效的Clash代理YAML文件。")
            except yaml.YAMLError as e:
                print(f"YAML 解析 {url} 错误: {e}")
            continue

        # 对于非YAML文件，按行解码和解析
        decoded_data = decode_base64(raw_data)
        lines = decoded_data.splitlines()
        for line in lines:
            line = line.strip()
            # 检查行是否以任何已知的协议前缀开头
            if not line or not any(line.startswith(s) for s in ['ss://','vmess://','trojan://','vless://','hysteria2://']):
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
            
            if proxy:
                identifier = (proxy['server'], proxy['port'])
                if identifier not in seen:
                    seen.add(identifier)
                    proxy['name'] = extract_flag(proxy.get('name', 'unknown')) # 使用.get避免KeyError
                    all_proxies.append(proxy)

    if not all_proxies:
        print("未找到有效的代理配置！")
        return

    # 保存到 data/clash.yaml
    os.makedirs('data', exist_ok=True)
    yaml_content = generate_yaml(all_proxies)
    output_path_data = 'data/clash.yaml'
    with open(output_path_data, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    print(f"Clash 配置文件已保存到 {output_path_data}")

    # 将结果按1860行分片输出到 sub 目录
    current_time = datetime.now()
    year_dir = current_time.strftime('%Y')
    month_dir = current_time.strftime('%m')
    date_prefix = current_time.strftime('%Y-%m-%d')
    
    sub_base_dir = os.path.join('sub', year_dir, month_dir)
    os.makedirs(sub_base_dir, exist_ok=True)

    proxies_per_file = 1860
    total_proxies = len(all_proxies)
    num_files = (total_proxies + proxies_per_file - 1) // proxies_per_file # 计算需要的文件数量

    for i in range(num_files):
        start_index = i * proxies_per_file
        end_index = min((i + 1) * proxies_per_file, total_proxies)
        part_proxies = all_proxies[start_index:end_index]

        part_yaml_content = generate_yaml(part_proxies)
        part_file_name = f"{date_prefix}_clash_part_{i+1}.yaml"
        part_output_path = os.path.join(sub_base_dir, part_file_name)
        
        with open(part_output_path, 'w', encoding='utf-8') as f:
            f.write(part_yaml_content)
        print(f"Clash 分片配置文件已保存到 {part_output_path} (包含 {len(part_proxies)} 条代理)")


if __name__ == "__main__":
    urls = [
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/ss.txt',
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/config.yaml',
        'https://raw.githubusercontent.com/qjlxg/hy2/refs/heads/main/configtg.txt',
    ]
    main(urls)
