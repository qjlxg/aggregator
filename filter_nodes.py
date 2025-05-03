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
import geoip2.database
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

def ignore_unknown_tag(loader, tag_suffix, node):
    return loader.construct_scalar(node)
yaml.SafeLoader.add_multi_constructor('', ignore_unknown_tag)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_PORT = 10000
CLASH_API_PORT = 11234
TEST_URL = "https://www.google.com/generate_204"
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
REQUEST_TIMEOUT = 8
RETRY_TIMES = 2
GEOIP_DB_PATH = './clash/Country.mmdb'
TCP_MAX_WORKERS = 20

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

COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵',
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

FIELD_ORDERS = {
    'vmess': ['name', 'server', 'port', 'type', 'uuid', 'alterId', 'tls', 'network', 'ws-opts', 'udp', 'cipher'],
    'ss': ['name', 'server', 'port', 'type', 'password', 'udp', 'cipher'],
    'hysteria2': ['name', 'server', 'port', 'type', 'password', 'auth', 'sni', 'skip-cert-verify', 'udp'],
    'trojan': ['name', 'server', 'port', 'type', 'password', 'sni', 'skip-cert-verify', 'udp'],
    'vless': ['name', 'server', 'port', 'type', 'uuid', 'tls', 'servername', 'network', 'reality-opts', 'client-fingerprint', 'udp']
}

class CustomDumper(yaml.Dumper):
    def represent_mapping(self, tag, mapping, flow_style=None):
        if isinstance(mapping, dict) and 'name' in mapping and 'server' in mapping:
            proxy_type = mapping.get('type', 'ss')
            order = FIELD_ORDERS.get(proxy_type, list(mapping.keys()))
            ordered_mapping = OrderedDict()
            for key in order:
                if key in mapping:
                    ordered_mapping[key] = mapping[key]
            for key in mapping:
                if key not in ordered_mapping:
                    ordered_mapping[key] = mapping[key]
            return super().represent_mapping(tag, ordered_mapping, flow_style=True)
        return super().represent_mapping(tag, mapping, flow_style=True)

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write("proxies:\n")
            for proxy in data['proxies']:
                proxy_str = yaml.dump(proxy, Dumper=CustomDumper, allow_unicode=True, default_flow_style=True, sort_keys=False)
                proxy_str = proxy_str.strip('\n')
                f.write(f" - {proxy_str}\n")
        logging.info(f"已保存 {path}")
    except Exception as e:
        logging.error(f"保存文件失败: {e}")

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
            if cipher == 'aes-128-gcm':
                cipher = 'chacha20-ietf-poly1305'
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

def tcp_ping(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def get_country_flag(ip_or_domain):
    try:
        ip_or_domain = str(ip_or_domain)
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_or_domain):
            ip = socket.gethostbyname(ip_or_domain)
        else:
            ip = ip_or_domain
        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            return COUNTRY_FLAGS.get(country_code, '🏁')
    except Exception:
        return '🏁'

def format_node_name(node, idx):
    name = str(node.get('name', ''))
    match = re.match(r'^([\U0001F1E6-\U0001F1FF][\U0001F1E6-\U0001F1FF])', name)
    if match:
        flag = match.group(1)
    else:
        flag = get_country_flag(node['server'])
    return f"{flag} bing{idx+1}"

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
        logging.error(f"Clash 启动端口 {BASE_PORT+1} 超时")
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
            logging.warning(f"停止 Clash 失败: {e}")
    if fname and os.path.exists(fname):
        try:
            os.remove(fname)
        except Exception as e:
            logging.warning(f"删除配置文件失败: {fname} {e}")

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
        logging.warning(f"切换节点到 {proxy_name} 失败: {e}")
        return False

def test_node_api(node, idx):
    proxy_name = node['name']
    if not switch_proxy_api(proxy_name):
        logging.info(f"切换到节点 {proxy_name} 失败")
        return None
    proxies = {'http': f'socks5://127.0.0.1:{BASE_PORT + 1}', 'https': f'socks5://127.0.0.1:{BASE_PORT + 1}'}
    ok = False
    for _ in range(RETRY_TIMES):
        try:
            r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            logging.info(f"节点 {proxy_name} 返回码: {r.status_code}")
            if r.status_code in [200, 204, 301, 302, 403, 429]:
                ok = True
                break
        except Exception as e:
            logging.error(f"节点 {proxy_name} 请求异常: {e}")
    if ok:
        logging.info(f"节点 {proxy_name} 测试成功")
        return node
    else:
        logging.info(f"节点 {proxy_name} 测试失败: 无法访问 {TEST_URL}")
        return None

def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'

    # 1. 读取所有节点
    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies', []):
        n = parse_url_node(x) if isinstance(x, str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n:
            nodes.append(n)
    logging.info(f"加载 {len(nodes)} 个节点")

    # 2. 先用TCP端口检测法快速筛选
    def tcp_check(node):
        host, port = node['server'], node['port']
        ok = tcp_ping(host, port)
        logging.info(f"TCP检测 {host}:{port} {'可用' if ok else '不可用'}")
        return ok

    tcp_valid = []
    with ThreadPoolExecutor(max_workers=TCP_MAX_WORKERS) as ex:
        futures = [ex.submit(tcp_check, node) for node in nodes]
        for idx, future in enumerate(as_completed(futures)):
            if future.result():
                tcp_valid.append(nodes[idx])

    logging.info(f"TCP检测通过节点数: {len(tcp_valid)}")

    # 3. 用一个Clash实例+API切换节点检测
    if not tcp_valid:
        logging.info("没有通过TCP检测的节点，未生成文件。")
        return

    clash_proc, clash_cfg = start_clash_with_all_nodes(tcp_valid)
    if not clash_proc:
        logging.error("Clash 启动失败，无法检测")
        return

    valid = []
    for idx, node in enumerate(tcp_valid):
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
        logging.info(f"最终有效节点数: {len(deduped)}")
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
