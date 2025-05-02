import yaml
import os
import subprocess
import requests
import time
import base64
import json
import urllib.parse

# 支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

# 测试的目标 URL
TEST_URLS = ['https://www.google.com', 'https://www.youtube.com']

def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def parse_node(node):
    """将 Clash 节点转换为可用的代理配置"""
    node_type = node.get('type', '').lower()
    if node_type not in SUPPORTED_TYPES:
        return None
    return node

def start_clash(node, clash_binary="clash-linux"):
    """启动 Clash 客户端并加载单个节点的配置"""
    # 创建临时的 Clash 配置文件
    temp_config = {
        'port': 7890,
        'socks-port': 7891,
        'mode': 'global',
        'proxies': [node],
        'proxy-groups': [
            {
                'name': 'Proxy',
                'type': 'select',
                'proxies': [node['name']]
            }
        ],
        'rules': ['MATCH,Proxy']
    }
    
    with open('temp_clash.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(temp_config, f, allow_unicode=True)
    
    # 启动 Clash 进程
    clash_process = subprocess.Popen(
        [f"./clash/{clash_binary}", "-f", "temp_clash.yaml", "-d", "./clash"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    # 等待 Clash 启动
    time.sleep(2)
    return clash_process

def test_proxy():
    """测试代理是否能访问 Google 和 YouTube"""
    proxies = {
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890'
    }
    
    for url in TEST_URLS:
        try:
            response = requests.get(url, proxies=proxies, timeout=10)
            if response.status_code == 200:
                print(f"成功访问 {url}")
            else:
                print(f"无法访问 {url}，状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"访问 {url} 失败: {e}")
            return False
    return True

def parse_url_node(url):
    """解析 vmess://, ss:// 等格式的节点"""
    try:
        if url.startswith('vmess://'):
            # 解析 vmess 节点
            vmess_data = base64.b64decode(url[8:]).decode('utf-8')
            vmess = json.loads(vmess_data)
            return {
                'name': vmess.get('ps', 'vmess_node'),
                'type': 'vmess',
                'server': vmess.get('add'),
                'port': int(vmess.get('port')),
                'uuid': vmess.get('id'),
                'alterId': int(vmess.get('aid', 0)),
                'cipher': vmess.get('scy', 'auto'),
                'network': vmess.get('net', 'tcp'),
                'tls': vmess.get('tls', False)
            }
        elif url.startswith('ss://'):
            # 解析 ss 节点
            parsed = urllib.parse.urlparse(url)
            method_password = base64.b64decode(parsed.netloc.split('@')[0]).decode('utf-8')
            method, password = method_password.split(':')
            server_port = parsed.netloc.split('@')[1].split(':')
            server, port = server_port[0], server_port[1].split('#')[0]
            name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'ss_node'
            return {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': int(port),
                'cipher': method,
                'password': password
            }
        elif url.startswith('trojan://'):
            # 解析 trojan 节点
            parsed = urllib.parse.urlparse(url)
            password = parsed.netloc.split('@')[0]
            server_port = parsed.netloc.split('@')[1].split(':')
            server, port = server_port[0], server_port[1].split('?')[0]
            name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'trojan_node'
            return {
                'name': name,
                'type': 'trojan',
                'server': server,
                'port': int(port),
                'password': password,
                'sni': server
            }
        elif url.startswith('vless://'):
            # 解析 vless 节点
            parsed = urllib.parse.urlparse(url)
            uuid = parsed.netloc.split('@')[0]
            server_port = parsed.netloc.split('@')[1].split(':')
            server, port = server_port[0], server_port[1].split('?')[0]
            name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'vless_node'
            return {
                'name': name,
                'type': 'vless',
                'server': server,
                'port': int(port),
                'uuid': uuid,
                'tls': True,
                'servername': server
            }
        elif url.startswith('hysteria2://'):
            # 解析 hysteria2 节点（简化）
            parsed = urllib.parse.urlparse(url)
            password = parsed.netloc.split('@')[0]
            server_port = parsed.netloc.split('@')[1].split(':')
            server, port = server_port[0], server_port[1].split('?')[0]
            name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'hysteria2_node'
            return {
                'name': name,
                'type': 'hysteria2',
                'server': server,
                'port': int(port),
                'password': password
            }
        else:
            return None
    except Exception as e:
        print(f"解析节点 {url} 失败: {e}")
        return None

def main():
    input_path = 'data/clash.yaml'
    output_path = 'data/google.yaml'

    if not os.path.exists(input_path):
        print(f"文件不存在: {input_path}")
        return

    clash_data = load_yaml(input_path)
    proxies = clash_data.get('proxies', [])

    valid_nodes = []

    for proxy in proxies:
        node = proxy
        if isinstance(node, str):  # 如果是 URL 格式
            node = parse_url_node(node)
        else:  # 已经是 Clash 格式
            node = parse_node(node)
        
        if not node:
            print(f"跳过无效节点: {proxy}")
            continue

        print(f"测试节点: {node['name']}")
        clash_process = start_clash(node, clash_binary='clash-linux')
        
        try:
            if test_proxy():
                valid_nodes.append(node)
                print(f"节点 {node['name']} 通过测试")
            else:
                print(f"节点 {node['name']} 未通过测试")
        finally:
            clash_process.terminate()
            time.sleep(1)  # 确保 Clash 进程结束

    print(f"共测试 {len(proxies)} 个节点，{len(valid_nodes)} 个通过测试")
    
    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, output_path)
        print(f"支持访问 Google 和 YouTube 的节点已保存到 {output_path}")
    else:
        print("没有节点通过测试，未生成输出文件")

if __name__ == "__main__":
    main()
