import os
import sys
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
import re
import socket
import geoip2.database
from collections import OrderedDict

def ignore_unknown_tag(loader, tag_suffix, node):
    return loader.construct_scalar(node)
yaml.SafeLoader.add_multi_constructor('', ignore_unknown_tag)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_PORT = 10000
TEST_URL = "https://www.google.com/generate_204"
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 2
BATCH_SIZE = 30
REQUEST_TIMEOUT = 8
RETRY_TIMES = 2
GEOIP_DB_PATH = './clash/Country.mmdb'

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

def start_clash(node, port):
    if not os.path.isfile(CLASH_PATH) or not os.access(CLASH_PATH, os.X_OK):
        logging.error(f"Clash 可执行文件 {CLASH_PATH} 不存在或不可执行")
        return None, None
    cfg = {
        'port': port,
        'socks-port': port + 1,
        'mode': 'global',
        'proxies': [node],
        'proxy-groups': [{'name': 'Proxy', 'type': 'select', 'proxies': [node['name']]}],
        'rules': ['MATCH,Proxy'],
        'dns': {
            'enable': True,
            'listen': '0.0.0.0:53',
            'default-nameserver': ['8.8.8.8', '1.1.1.1'],
            'nameserver': ['8.8.8.8', '1.1.1.1']
        }
    }
    fname = f'temp_{port}.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True)
    try:
        p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        if not wait_port(port + 1, timeout=30):
            logging.error(f"Clash 启动端口 {port+1} 超时")
            stop_clash(p, fname)
            return None, fname
        time.sleep(3)  # 启动后再等几秒，确保节点加载
        # 输出clash日志
        try:
            out, err = p.communicate(timeout=1)
            if out:
                logging.debug(f"Clash stdout: {out.decode(errors='ignore')}")
            if err:
                logging.debug(f"Clash stderr: {err.decode(errors='ignore')}")
        except Exception:
            pass
        return p, fname
    except Exception as e:
        logging.error(f"启动 Clash 失败: {e}")
        return None, fname

def stop_clash(p, fname):
    if p:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            p.wait(timeout=2)
        except Exception as e:
            logging.warning(f"停止 Clash 失败: {e}")
    if fname and os.path.exists(fname):
        try:
            os.remove(fname)
        except Exception as e:
            logging.warning(f"删除配置文件失败: {fname} {e}")

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

def test_node(node, idx):
    port = BASE_PORT + (idx % 100) * 2
    logging.info(f"测试节点: {node['name']} (端口: {port})")
    p, cfg = start_clash(node, port)
    if not p:
        logging.error(f"节点 {node['name']} 测试失败: Clash 未启动")
        stop_clash(p, cfg)
        return None

    proxies = {'http': f'socks5://127.0.0.1:{port + 1}', 'https': f'socks5://127.0.0.1:{port + 1}'}
    ok = False
    for _ in range(RETRY_TIMES):
        try:
            r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            logging.info(f"节点 {node['name']} 返回码: {r.status_code}")
            if r.status_code in [200, 204, 301, 302, 403, 429]:
                ok = True
                break
        except Exception as e:
            logging.error(f"节点 {node['name']} 请求异常: {e}")
    stop_clash(p, cfg)
    if ok:
        logging.info(f"节点 {node['name']} 测试成功")
        return node
    else:
        logging.info(f"节点 {node['name']} 测试失败: 无法访问 {TEST_URL}")
        return None

def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'

    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies', []):
        n = parse_url_node(x) if isinstance(x, str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n:
            nodes.append(n)
    logging.info(f"加载 {len(nodes)} 个节点")

    valid = []
    total = len(nodes)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = nodes[batch_start:batch_start+BATCH_SIZE]
        logging.info(f"处理第 {batch_start+1} ~ {batch_start+len(batch)} 个节点")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(test_node, node, idx+batch_start) for idx, node in enumerate(batch)]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid.append(result)
        time.sleep(2)

    # 节点去重（按 server+port+type 唯一）
    seen = set()
    deduped = []
    for node in valid:
        key = f"{node['server']}:{node['port']}:{node['type']}"
        if key not in seen:
            seen.add(key)
            deduped.append(node)

    # 格式化节点名
    for idx, node in enumerate(deduped):
        node['name'] = format_node_name(node, idx)

    if deduped:
        save_yaml({'proxies': deduped}, out)
        logging.info(f"有效节点数: {len(deduped)}")
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
