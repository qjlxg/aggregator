import os
import json
import base64
import urllib.parse
import yaml
import subprocess
import time
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import requests
import socket

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量
BASE_PORT = 10000
TEST_URLS = ["https://www.google.com", "https://www.youtube.com", "https://www.cloudflare.com"]  # 增加测试 URL
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 20
REQUEST_TIMEOUT = 15  # 增加超时时间
STARTUP_DELAY = 5     # 增加启动延迟

# 检查端口是否被占用
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# 获取可用端口
def get_available_port(base_port):
    port = base_port
    while is_port_in_use(port):
        port += 1
    return port

# 生成 Clash 配置文件
def generate_clash_config(node, port, config_path):
    config = {
        'port': port,
        'socks-port': port,
        'mode': 'rule',
        'log-level': 'silent',
        'proxies': [node]
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)

# 使用 curl 测试代理
def test_with_curl(url, proxy_port):
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--socks5', f'127.0.0.1:{proxy_port}', url],
            capture_output=True, text=True, timeout=REQUEST_TIMEOUT
        )
        status_code = int(result.stdout)
        if status_code == 200:
            return True
        else:
            logging.warning(f"curl returned status code {status_code} for URL {url}")
    except Exception as e:
        logging.error(f"curl test failed for URL {url}: {e}")
    return False

# 测试单个节点
def test_node(node, idx):
    base_port = BASE_PORT + (idx % 100) * 2
    port = get_available_port(base_port)
    config_path = f'config_{port}.yaml'
    
    # 生成配置文件
    generate_clash_config(node, port, config_path)
    
    # 启动 Clash
    clash_process = subprocess.Popen(['clash', '-f', config_path])
    time.sleep(STARTUP_DELAY)
    
    proxies = {'http': f'socks5://127.0.0.1:{port}', 'https': f'socks5://127.0.0.1:{port}'}
    is_working = False
    
    # 使用 requests 测试
    for url in TEST_URLS:
        try:
            logging.info(f"Testing node {node['name']} with URL {url} using requests")
            response = requests.get(url, proxies=proxies, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                logging.info(f"Node {node['name']} is working with URL {url} (requests)")
                is_working = True
                break
            else:
                logging.warning(f"Node {node['name']} returned status code {response.status_code} for URL {url}")
        except requests.RequestException as e:
            logging.error(f"Node {node['name']} failed with URL {url} using requests: {e}")
    
    # 如果 requests 失败，尝试 curl
    if not is_working:
        for url in TEST_URLS:
            if test_with_curl(url, port):
                logging.info(f"Node {node['name']} is working with URL {url} (curl)")
                is_working = True
                break
    
    # 停止 Clash
    os.kill(clash_process.pid, signal.SIGTERM)
    if os.path.exists(config_path):
        os.remove(config_path)
    
    return is_working

# 解析代理节点（简化的解析逻辑）
def parse_node(node_str):
    if not isinstance(node_str, str):
        logging.error(f"Invalid node format: {node_str}")
        return None
    
    node = {}
    if node_str.startswith('vmess://'):
        try:
            vmess_data = base64.urlsafe_b64decode(node_str[8:]).decode('utf-8')
            vmess = json.loads(vmess_data)
            node = {
                'name': vmess.get('ps', 'unnamed'),
                'server': vmess['add'],
                'port': int(vmess['port']),
                'type': 'vmess',
                'uuid': vmess['id'],
                'alterId': vmess.get('aid', 0),
                'cipher': vmess.get('scy', 'auto'),
                'tls': vmess.get('tls', False),
                'network': vmess.get('net', 'tcp'),
                'udp': True
            }
        except Exception as e:
            logging.error(f"Failed to parse vmess node: {e}")
            return None
    elif node_str.startswith('ss://'):
        try:
            parts = node_str[5:].split('#')
            auth_server = parts[0].split('@')
            auth = base64.urlsafe_b64decode(auth_server[0]).decode('utf-8').split(':')
            server_port = auth_server[1].split(':')
            node = {
                'name': urllib.parse.unquote(parts[1]) if len(parts) > 1 else 'unnamed',
                'server': server_port[0],
                'port': int(server_port[1]),
                'type': 'ss',
                'cipher': auth[0],
                'password': auth[1],
                'udp': True
            }
        except Exception as e:
            logging.error(f"Failed to parse ss node: {e}")
            return None
    # 其他类型（trojan, vless, hysteria2）可类似扩展
    
    if node.get('type') not in SUPPORTED_TYPES:
        logging.warning(f"Unsupported proxy type: {node.get('type')}")
        return None
    
    return node

# 主函数
def main():
    # 读取节点列表（假设从文件中读取）
    with open('nodes.txt', 'r', encoding='utf-8') as f:
        node_strings = [line.strip() for line in f if line.strip()]
    
    nodes = []
    for node_str in node_strings:
        node = parse_node(node_str)
        if node:
            nodes.append(node)
    
    # 并行测试节点
    working_nodes = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_node = {executor.submit(test_node, node, idx): node for idx, node in enumerate(nodes)}
        for future in as_completed(future_to_node):
            node = future_to_node[future]
            try:
                if future.result():
                    working_nodes.append(node)
            except Exception as e:
                logging.error(f"Error testing node {node['name']}: {e}")
    
    # 保存可用节点到 YAML 文件
    if working_nodes:
        with open('working_nodes.yaml', 'w', encoding='utf-8') as f:
            yaml.dump({'proxies': working_nodes}, f, allow_unicode=True)
        logging.info(f"Saved {len(working_nodes)} working nodes to working_nodes.yaml")
    else:
        logging.warning("No working nodes found")

if __name__ == "__main__":
    main()
