import os
import sys
import json
import base64
import urllib.parse
import yaml
import subprocess
import time
import requests
import logging
import re
import socket
import asyncio
from collections import OrderedDict

# ----------- TCP异步检测部分 -----------
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']

def parse_url_node(url):
    try:
        if url.startswith('vmess://'):
            vmess_raw = url[8:]
            vmess_raw += '=' * (-len(vmess_raw) % 4)
            data = json.loads(base64.b64decode(vmess_raw).decode('utf-8', errors='ignore'))
            return {
                'name': data.get('ps', 'vmess'),
                'server': data['add'],
                'port': int(data['port']),
                'type': 'vmess',
                'uuid': data['id'],
                'alterId': int(data.get('aid', 0)),
                'cipher': data.get('scy', 'auto'),
                'network': data.get('net', 'tcp'),
                'tls': bool(data.get('tls', False))
            }
        if url.startswith('ss://'):
            parsed = urllib.parse.urlparse(url)
            base64_part = parsed.netloc.split('@')[0]
            method_pass = base64.b64decode(base64_part + '=' * (-len(base64_part) % 4)).decode('utf-8', errors='ignore')
            if '@' in parsed.netloc:
                method, passwd = method_pass.split(':', 1)
                server, port = parsed.netloc.split('@')[1].split(':')
            else:
                method, rest = method_pass.split(':', 1)
                passwd, server_port = rest.rsplit('@', 1)
                server, port = server_port.split(':')
            cipher = method
            return {
                'name': urllib.parse.unquote(parsed.fragment) or 'ss',
                'server': server,
                'port': int(port),
                'type': 'ss',
                'password': passwd,
                'udp': True,
                'cipher': cipher
            }
        if url.startswith('trojan://'):
            p = urllib.parse.urlparse(url)
            pwd = p.netloc.split('@')[0]
            server, port = p.netloc.split('@')[1].split(':')
            return {
                'name': urllib.parse.unquote(p.fragment) or 'trojan',
                'server': server,
                'port': int(port),
                'type': 'trojan',
                'password': pwd,
                'sni': server
            }
        if url.startswith('vless://'):
            p = urllib.parse.urlparse(url)
            uuid = p.netloc.split('@')[0]
            server, port = p.netloc.split('@')[1].split(':')
            return {
                'name': urllib.parse.unquote(p.fragment) or 'vless',
                'server': server,
                'port': int(port),
                'type': 'vless',
                'uuid': uuid,
                'tls': True,
                'servername': server
            }
        if url.startswith('hysteria2://'):
            p = urllib.parse.urlparse(url)
            pwd = p.netloc.split('@')[0]
            server, port = p.netloc.split('@')[1].split(':')
            return {
                'name': urllib.parse.unquote(p.fragment) or 'hysteria2',
                'server': server,
                'port': int(port),
                'type': 'hysteria2',
                'password': pwd
            }
    except Exception:
        return None
    return None

async def tcp_ping(host, port, timeout=0.5):
    try:
        loop = asyncio.get_event_loop()
        fut = loop.create_connection(lambda: asyncio.Protocol(), host, port)
        _, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        return True
    except Exception:
        return False

async def batch_tcp_check(nodes, max_concurrent=500):
    import re
    sem = asyncio.Semaphore(max_concurrent)
    results = []

    async def check_one(node):
        async with sem:
            host, port = node['server'], node['port']
            # DNS resolve
            try:
                if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', str(host)):
                    host = socket.gethostbyname(host)
            except Exception:
                return None
            ok = await tcp_ping(host, port)
            if ok:
                return node
            return None

    tasks = [check_one(node) for node in nodes]
    for fut in asyncio.as_completed(tasks):
        result = await fut
        if result:
            results.append(result)
    return results

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

# ----------- Clash检测部分 -----------
BASE_PORT = 10000
CLASH_API_PORT = 11234
TEST_URL = "https://www.google.com/generate_204"
REQUEST_TIMEOUT = 8
RETRY_TIMES = 2

def get_clash_path():
    plat = sys.platform
    if plat.startswith('win'):
        return os.path.join('clash', 'clash-windows.exe')
    elif plat == 'darwin':
        if 'arm' in os.uname().machine:
            return os.path.join('clash', 'clash-darwin-arm')
        else:
            return os.path.join('clash', 'clash-darwin-amd')
    else:
        return os.path.join('clash', 'clash-linux')

CLASH_PATH = get_clash_path()

def wait_port(port, timeout=30):
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

def start_clash_with_all_nodes(nodes):
    clash_cfg = {
        'port': BASE_PORT,
        'socks-port': BASE_PORT + 1,
        'mode': 'global',
        'proxies': nodes,
        'proxy-groups': [{
            'name': 'Proxy',
            'type': 'select',
            'proxies': [n['name'] for n in nodes]
        }],
        'rules': ['MATCH,Proxy'],
        'external-controller': f'127.0.0.1:{CLASH_API_PORT}',
        'secret': '',
        'dns': {
            'enable': True,
            'listen': '0.0.0.0:53',
            'default-nameserver': ['8.8.8.8', '1.1.1.1'],
            'nameserver': ['8.8.8.8', '1.1.1.1']
        }
    }
    fname = 'temp_all.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(clash_cfg, f, allow_unicode=True)
    p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not wait_port(BASE_PORT + 1, timeout=30):
        print(f"Clash 启动端口 {BASE_PORT+1} 超时")
        p.terminate()
        return None, fname
    time.sleep(3)
    return p, fname

def stop_clash(p, fname):
    if p:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception as e:
            print(f"停止 Clash 失败: {e}")
    if fname and os.path.exists(fname):
        try:
            os.remove(fname)
        except Exception as e:
            print(f"删除配置文件失败: {fname} {e}")

def switch_proxy_api(proxy_name):
    url = f"http://127.0.0.1:{CLASH_API_PORT}/proxies/Proxy"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return False
        data = r.json()
        if data.get('now') == proxy_name:
            return True
        r2 = requests.put(url, json={"name": proxy_name}, timeout=5)
        return r2.status_code == 204
    except Exception as e:
        print(f"切换节点到 {proxy_name} 失败: {e}")
        return False

def test_node_api(node, idx):
    proxy_name = node['name']
    if not switch_proxy_api(proxy_name):
        print(f"切换到节点 {proxy_name} 失败")
        return None
    proxies = {'http': f'socks5://127.0.0.1:{BASE_PORT + 1}', 'https': f'socks5://127.0.0.1:{BASE_PORT + 1}'}
    ok = False
    for _ in range(RETRY_TIMES):
        try:
            r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            print(f"节点 {proxy_name} 返回码: {r.status_code}")
            if r.status_code in [200, 204, 301, 302, 403, 429]:
                ok = True
                break
        except Exception as e:
            print(f"节点 {proxy_name} 请求异常: {e}")
    if ok:
        print(f"节点 {proxy_name} 测试成功")
        return node
    else:
        print(f"节点 {proxy_name} 测试失败: 无法访问 {TEST_URL}")
        return None

def format_node_name(node, idx):
    return f"bing{idx+1}"

def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    tcp_out = 'data/tcp_checked.yaml'
    out = 'data/google.yaml'

    # 1. 读取所有节点
    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies', []):
        n = parse_url_node(x) if isinstance(x, str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n:
            nodes.append(n)
    print(f"加载 {len(nodes)} 个节点，开始异步TCP检测...")

    # 2. 异步TCP检测
    valid_nodes = asyncio.run(batch_tcp_check(nodes, max_concurrent=500))
    print(f"TCP检测通过节点数: {len(valid_nodes)}")
    save_yaml({'proxies': valid_nodes}, tcp_out)

    # 3. 用Clash检测
    if not valid_nodes:
        print("没有通过TCP检测的节点，未生成文件。")
        return

    clash_proc, clash_cfg = start_clash_with_all_nodes(valid_nodes)
    if not clash_proc:
        print("Clash 启动失败，无法检测")
        return

    valid = []
    for idx, node in enumerate(valid_nodes):
        node['name'] = format_node_name(node, idx)
        result = test_node_api(node, idx)
        if result:
            valid.append(result)
        time.sleep(0.5)  # 防止切换过快

    stop_clash(clash_proc, clash_cfg)

    # 节点去重
    seen = set()
    deduped = []
    for node in valid:
        key = f"{node['server']}:{node['port']}:{node['type']}"
        if key not in seen:
            seen.add(key)
            deduped.append(node)

    if deduped:
        save_yaml({'proxies': deduped}, out)
        print(f"最终有效节点数: {len(deduped)}，已保存到 {out}")
    else:
        print("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
