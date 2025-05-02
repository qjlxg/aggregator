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

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量定义
BASE_PORT = 10000
TEST_URLS = [
    "http://www.google.com",
    "http://www.youtube.com",
    "http://www.facebook.com"
]
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']

def load_yaml(file_path):
    """加载 YAML 文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"加载 {file_path} 失败: {e}")
        return None

def save_yaml(data, file_path):
    """保存 YAML 文件"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)
        logging.info(f"成功保存到 {file_path}")
    except Exception as e:
        logging.error(f"保存 {file_path} 失败: {e}")

def parse_node(node):
    """验证节点配置"""
    required_fields = ['server', 'port', 'type']
    if not all(field in node for field in required_fields):
        logging.warning(f"节点配置缺少必要字段: {node}")
        return None
    node_type = node.get('type', '').lower()
    if node_type not in SUPPORTED_TYPES:
        logging.warning(f"不支持的节点类型: {node_type}")
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
        logging.error(f"解析节点 {url} 失败: {e}")
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
        time.sleep(3)  # 增加等待时间，确保 Clash 完全启动
        if process.poll() is not None:
            logging.error(f"Clash 启动失败，端口 {port}")
            return None, temp_config_file
        logging.info(f"Clash 启动成功，PID: {process.pid}，端口: {port}")
        return process, temp_config_file
    except Exception as e:
        logging.error(f"启动 Clash（端口 {port}）失败: {e}")
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
            logging.error(f"终止 Clash 失败: {e}")
    if os.path.exists(temp_config_file):
        os.remove(temp_config_file)

def test_proxy_connectivity(node_name, port):
    """通过代理测试网络连通性"""
    max_retries = 2
    for url in TEST_URLS:
        for attempt in range(max_retries + 1):
            cmd = [
                "curl", "-x", f"socks5://127.0.0.1:{port + 1}",
                "--connect-timeout", "5", "--max-time", "10",
                "-s", "-w", "%{http_code}|%{time_total}", url
            ]
            try:
                result = subprocess.run(cmd, timeout=15, capture_output=True, text=True)
                output = result.stdout.strip().split('|')
                http_code, time_total = output[0], float(output[1])
                if result.returncode == 0 and http_code == "200":
                    logging.info(f"节点 {node_name} 访问 {url} 成功，HTTP状态码: {http_code}，耗时: {time_total:.2f}s")
                    break  # 该站点测试成功，跳到下一个站点
                else:
                    logging.warning(f"节点 {node_name} 访问 {url} 失败（尝试 {attempt + 1}），HTTP状态码: {http_code}")
                    if attempt == max_retries:
                        return False
            except subprocess.TimeoutExpired:
                logging.warning(f"节点 {node_name} 访问 {url} 超时（尝试 {attempt + 1}）")
                if attempt == max_retries:
                    return False
            except Exception as e:
                logging.error(f"测试节点 {node_name} 访问 {url} 出错（尝试 {attempt + 1}）: {e}")
                if attempt == max_retries:
                    return False
            time.sleep(1)  # 重试间隔
    return True

def test_node(node, thread_index):
    """测试单个节点"""
    port = BASE_PORT + (thread_index % 2) * 2  # 限制为2个并发线程的端口范围
    node_name = node['name']
    
    logging.info(f"线程 {thread_index} 测试节点: {node_name}（端口 {port}）")
    
    clash_process, temp_config_file = start_clash(node, port, clash_binary='clash-linux')
    if not clash_process:
        logging.error(f"节点 {node_name} 无法启动 Clash")
        return None
    
    try:
        if test_proxy_connectivity(node_name, port):
            return node
        else:
            return None
    finally:
        terminate_clash(clash_process, temp_config_file)
        time.sleep(1)  # 确保端口释放

def main():
    input_path = 'data/clash.yaml'
    output_path = 'data/google.yaml'

    if not os.path.exists(input_path):
        logging.error(f"输入文件 {input_path} 不存在")
        return

    clash_data = load_yaml(input_path)
    if not clash_data or 'proxies' not in clash_data:
        logging.error(f"{input_path} 中未找到代理节点")
        return

    proxies = clash_data.get('proxies', [])
    valid_nodes = []

    # 使用线程池并行测试，限制最大线程数
    max_workers = 2
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

    logging.info(f"共测试 {len(proxies)} 个节点，{len(valid_nodes)} 个通过测试")
    
    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, output_path)
    else:
        logging.info("没有节点通过测试，未生成输出文件")

if __name__ == "__main__":
    main()
