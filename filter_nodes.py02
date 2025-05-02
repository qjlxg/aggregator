import yaml
import os
import subprocess
import requests
import time
import base64
import json
import urllib.parse
import signal

# 支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

# 测试的 URL
TEST_URLS = ['https://www.google.com', 'https://www.youtube.com']

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

def start_clash(node, clash_binary="clash-linux"):
    """启动 Clash 客户端"""
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
    
    try:
        with open('temp_clash.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(temp_config, f, allow_unicode=True)
        
        process = subprocess.Popen(
            [f"./clash/{clash_binary}", "-f", "temp_clash.yaml", "-d", "./clash"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        time.sleep(2)  # 等待 Clash 启动
        return process
    except Exception as e:
        print(f"启动 Clash 失败: {e}")
        return None

def terminate_clash(process):
    """强制终止 Clash 进程"""
    if process:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception as e:
            print(f"终止 Clash 失败: {e}")

def test_proxy():
    """测试代理是否能访问 Google 和 YouTube"""
    proxies = {
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890'
    }
    
    for url in TEST_URLS:
        try:
            response = requests.get(url, proxies=proxies, timeout=10)
            if response.status_code != 200:
                print(f"访问 {url} 失败，状态码: {response.status_code}")
                return False
            print(f"成功访问 {url}")
        except Exception as e:
            print(f"访问 {url} 失败: {e}")
            return False
    return True

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

    for proxy in proxies:
        node = proxy
        if isinstance(node, str):  # URL 格式
            node = parse_url_node(node)
        else:  # Clash 格式
            node = parse_node(node)
        
        if not node:
            print(f"跳过无效节点: {proxy}")
            continue

        print(f"正在测试节点: {node['name']}")
        clash_process = start_clash(node, clash_binary='clash-linux')
        
        if not clash_process:
            print(f"无法为节点 {node['name']} 启动 Clash")
            continue

        try:
            if test_proxy():
                valid_nodes.append(node)
                print(f"节点 {node['name']} 测试通过")
            else:
                print(f"节点 {node['name']} 测试失败")
        except Exception as e:
            print(f"测试节点 {node['name']} 出错: {e}")
        finally:
            terminate_clash(clash_process)
            time.sleep(1)  # 确保端口释放

    print(f"共测试 {len(proxies)} 个节点，{len(valid_nodes)} 个通过测试")
    
    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, output_path)
        print(f"通过测试的节点已保存到 {output_path}")
    else:
        print("没有节点通过测试，未生成输出文件")

if __name__ == "__main__":
    main()
