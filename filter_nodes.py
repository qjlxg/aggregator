import yaml
import os
import subprocess
import time
import base64
import json
import urllib.parse
import signal
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dns.resolver import Resolver

# 支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

# 测试的域名
TEST_DOMAINS = ['www.google.com', 'www.youtube.com']

# 基础端口号（每个线程递增）
BASE_PORT = 7890

def load_yaml(file_path):
    """加载 YAML 文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"加载 {file_path} 失败: {e}")
        return None

def save_yaml(data, file_path):
    """保存 YAML 文件"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)
    except Exception as e:
        print(f"保存 {file_path} 失败: {e}")

def parse_node(node):
    """验证节点配置"""
    node_type = node.get('type', '').lower()
    if node_type not in SUPPORTED_TYPES:
        print(f"不支持的节点类型: {node_type}")
        return None
    return node

def parse_url_node(url):
    """解析 vmess://, ss:// 等格式的节点"""
    try:
        if url.startswith('vmess://'):
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

def start_clash(node, port, clash_binary="clash-linux"):
    """启动 Clash 客户端，使用指定端口"""
    temp_config = {
        'port': port,
        'socks-port': port + 1,
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
    
    temp_config_file = f'temp_clash_{port}.yaml'
    try:
        with open(temp_config_file, 'w', encoding='utf-8') as f:
            yaml.dump(temp_config, f, allow_unicode=True)
        
        process = subprocess.Popen(
            [f"./clash/{clash_binary}", "-f", temp_config_file, "-d", "./clash"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        time.sleep(2)  # 等待 Clash 启动
        return process, temp_config_file
    except Exception as e:
        print(f"启动 Clash（端口 {port}）失败: {e}")
        return None, temp_config_file

def terminate_clash(process, temp_config_file):
    """强制终止 Clash 进程并清理临时文件"""
    if process:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception as e:
            print(f"终止 Clash 失败: {e}")
    if os.path.exists(temp_config_file):
        os.remove(temp_config_file)

def test_proxy_dns(node_name, port):
    """通过代理测试 DNS 解析"""
    resolver = Resolver()
    resolver.nameservers = ['8.8.8.8']  # 使用 Google DNS
    resolver.port = port + 1  # 使用 socks 端口
    resolver.timeout = 5
    resolver.lifetime = 5

    # 配置代理
    os.environ['ALL_PROXY'] = f'socks5://127.0.0.1:{port + 1}'

    for domain in TEST_DOMAINS:
        try:
            answers = resolver.resolve(domain, 'A')
            ips = [rdata.address for rdata in answers]
            print(f"节点 {node_name} 成功解析 {domain}: {ips}")
            # 简单验证 IP（可根据需要扩展）
            if not ips:
                print(f"节点 {node_name} 解析 {domain} 失败：无 IP 返回")
                return False
        except Exception as e:
            print(f"节点 {node_name} 解析 {domain} 失败: {e}")
            return False
        finally:
            os.environ.pop('ALL_PROXY', None)
    return True

def test_node(node, thread_index):
    """测试单个节点"""
    port = BASE_PORT + thread_index * 2  # 动态分配端口
    node_name = node['name']
    
    print(f"线程 {thread_index} 测试节点: {node_name}（端口 {port}）")
    
    clash_process, temp_config_file = start_clash(node, port, clash_binary='clash-linux')
    if not clash_process:
        print(f"节点 {node_name} 无法启动 Clash")
        return None
    
    try:
        if test_proxy_dns(node_name, port):
            print(f"节点 {node_name} 测试通过")
            return node
        else:
            print(f"节点 {node_name} 测试失败")
            return None
    except Exception as e:
        print(f"测试节点 {node_name} 出错: {e}")
        return None
    finally:
        terminate_clash(clash_process, temp_config_file)
        time.sleep(1)  # 确保端口释放

def main():
    input_path = 'data/clash.yaml'
    output_path = 'data/google.yaml'

    if not os.path.exists(input_path):
        print(f"输入文件 {input_path} 不存在")
        return

    clash_data = load_yaml(input_path)
    if not clash_data or 'proxies' not in clash_data:
        print(f"{input_path} 中未找到代理节点")
        return

    proxies = clash_data.get('proxies', [])
    valid_nodes = []

    # 使用线程池并行测试
    max_workers = 4  # 控制最大线程数，避免资源耗尽
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_node = {
            executor.submit(test_node, node, idx): node
            for idx, proxy in enumerate(proxies)
            if (node := (parse_url_node(proxy) if isinstance(proxy, str) else parse_node(proxy)))
        }
        
        for future in as_completed(future_to_node):
            node = future.result()
            if node:
                valid_nodes.append(node)

    print(f"共测试 {len(proxies)} 个节点，{len(valid_nodes)} 个通过测试")
    
    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, output_path)
        print(f"通过测试的节点已保存到 {output_path}")
    else:
        print("没有节点通过测试，未生成输出文件")

if __name__ == "__main__":
    main()
