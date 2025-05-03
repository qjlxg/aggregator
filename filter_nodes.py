import os
import yaml
import subprocess
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_PORT = 20000
TEST_URL = "https://www.google.com"  # 使用全球可访问的URL
REQUEST_TIMEOUT = 5
BATCH_SIZE = 500  # 每批检测500个节点
CLASH_PATH = './clash/clash-linux'

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)
    logging.info(f"已保存 {path}")

def wait_port(port, timeout=8):
    start = time.time()
    while time.time() - start < timeout:
        s = socket.socket()
        try:
            s.connect(('127.0.0.1', port))
            s.close()
            return True
        except Exception:
            time.sleep(0.2)
    return False

def start_clash(nodes, port):
    cfg = {
        'port': port,
        'socks-port': port + 1,
        'mode': 'global',
        'proxies': nodes,
        'proxy-groups': [{'name': 'Proxy', 'type': 'select', 'proxies': [node['name'] for node in nodes]}],
        'rules': ['MATCH,Proxy']
    }
    fname = f'temp_clash_{port}.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True)
    p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not wait_port(port + 1, timeout=8):
        logging.error(f"Clash 启动端口 {port+1} 超时")
        p.terminate()
        os.remove(fname)
        return None, None
    return p, fname

def stop_clash(p, fname):
    if p:
        p.terminate()
        p.wait()
    if os.path.exists(fname):
        os.remove(fname)

def test_node(node, port):
    proxies = {'http': f'socks5://127.0.0.1:{port + 1}', 'https': f'socks5://127.0.0.1:{port + 1}'}
    try:
        r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
        if r.status_code in [200, 301, 302]:
            logging.info(f"节点 {node['name']} 测试成功，状态码: {r.status_code}")
            return True
        else:
            logging.info(f"节点 {node['name']} 测试失败，状态码: {r.status_code}")
    except Exception as e:
        logging.info(f"节点 {node['name']} 测试失败: {e}")
    return False

def main():
    inp = 'data/clash.yaml'
    out = 'data/valid_nodes.yaml'
    
    # 加载节点
    d = load_yaml(inp)
    nodes = d.get('proxies', [])
    logging.info(f"加载 {len(nodes)} 个节点")

    valid_nodes = []
    # 分批检测
    for i in range(0, len(nodes), BATCH_SIZE):
        batch_nodes = nodes[i:i + BATCH_SIZE]
        port = BASE_PORT + (i // BATCH_SIZE) * 2
        logging.info(f"检测第 {i+1} 至 {i+len(batch_nodes)} 个节点，端口: {port}")
        
        p, cfg = start_clash(batch_nodes, port)
        if not p:
            continue
        
        for node in batch_nodes:
            if test_node(node, port):
                valid_nodes.append(node)
        
        stop_clash(p, cfg)

    # 保存有效节点
    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, out)
        logging.info(f"有效节点数: {len(valid_nodes)}")
    else:
        logging.info("没有有效节点")

if __name__ == "__main__":
    main()
