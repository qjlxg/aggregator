import os
import json
import base64
import urllib.parse
import yaml
import subprocess
import time
import signal
import logging
import requests
import re
import socket
import geoip2.database
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_PORT = 10000
TEST_URL = "https://www.tiktok.com"
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 25
REQUEST_TIMEOUT = 5
GEOIP_DB_PATH = './clash/Country.mmdb'
CLASH_PATH = './clash/clash-linux'

COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵',
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

FIELD_ORDERS = {
    'vmess': ['name', 'server', 'port', 'type', 'uuid', 'alterId', 'cipher', 'tls', 'network', 'ws-opts', 'udp'],
    'ss': ['name', 'server', 'port', 'type', 'cipher', 'password', 'udp'],
    'hysteria2': ['name', 'server', 'port', 'type', 'password', 'auth', 'sni', 'skip-cert-verify', 'udp'],
    'trojan': ['name', 'server', 'port', 'type', 'password', 'sni', 'skip-cert-verify', 'udp'],
    'vless': ['name', 'server', 'port', 'type', 'uuid', 'tls', 'servername', 'network', 'reality-opts', 'client-fingerprint', 'udp']
}

class CustomDumper(yaml.Dumper):
    def represent_mapping(self, tag, mapping, flow_style=None):
        if isinstance(mapping, dict) and 'name' in mapping and 'server' in mapping:
            proxy_type = mapping.get('type', 'ss')
            order = FIELD_ORDERS.get(proxy_type, ['name', 'server', 'port', 'type'])
            ordered_mapping = {key: mapping[key] for key in order if key in mapping}
            return super().represent_mapping(tag, ordered_mapping, flow_style=True)
        return super().represent_mapping(tag, mapping, flow_style=False)

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write("proxies:\n")
            for proxy in data['proxies']:
                proxy_str = yaml.dump([proxy], Dumper=CustomDumper, allow_unicode=True, default_flow_style=True)
                proxy_str = proxy_str.strip('[]\n')
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
                'name': data.get('ps'),
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
                'cipher': cipher,
                'password': passwd
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
    except Exception as e:
        logging.warning(f"解析节点失败: {e}")
    return None

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
    if not os.path.isfile(CLASH_PATH) or not os.access(CLASH_PATH, os.X_OK):
        logging.error(f"Clash 可执行文件 {CLASH_PATH} 不存在或不可执行")
        return None, None
    cfg = {
        'port': port,
        'socks-port': port + 1,
        'mode': 'global',
        'proxies': nodes,
        'proxy-groups': [{'name': 'Proxy', 'type': 'select', 'proxies': [node['name'] for node in nodes]}],
        'rules': ['MATCH,Proxy']
    }
    fname = 'temp_clash.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True)
    try:
        p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        if not wait_port(port + 1, timeout=8):
            logging.error(f"Clash 启动端口 {port+1} 超时")
            stop_clash(p, fname)
            return None, fname
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
        os.remove(fname)

def test_nodes(nodes, port):
    p, cfg = start_clash(nodes, port)
    if not p:
        logging.error("Clash 未启动，测试中止")
        return []

    socks_port = port + 1
    clash_api_url = f"http://127.0.0.1:{port}/proxies"
    valid_nodes = []

    # 获取所有代理节点的延迟
    try:
        response = requests.get(clash_api_url, timeout=5)
        response.raise_for_status()
        proxies_data = response.json().get('proxies', {})
        proxy_names = [node['name'] for node in nodes]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(test_proxy_delay, name, socks_port): name for name in proxy_names}
            for future in as_completed(futures):
                name = futures[future]
                delay = future.result()
                if delay and delay < 5000:  # 延迟小于 5 秒的节点视为有效
                    for node in nodes:
                        if node['name'] == name:
                            logging.info(f"节点 {name} 测试成功，延迟: {delay}ms")
                            valid_nodes.append(node)
                            break
                else:
                    logging.info(f"节点 {name} 测试失败，延迟: {delay if delay else '超时'}")
    except Exception as e:
        logging.error(f"访问 Clash API 失败: {e}")

    stop_clash(p, cfg)
    return valid_nodes

def test_proxy_delay(proxy_name, socks_port):
    proxies = {'http': f'socks5://127.0.0.1:{socks_port}', 'https': f'socks5://127.0.0.1:{socks_port}'}
    start_time = time.time()
    try:
        r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code in [200, 301, 302, 403, 429]:
            delay = int((time.time() - start_time) * 1000)
            return delay
    except Exception:
        return None
    return None

def get_country_flag(ip_or_domain, cache={}):
    if ip_or_domain in cache:
        return cache[ip_or_domain]
    try:
        ip_or_domain = str(ip_or_domain)
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_or_domain):
            ip = socket.gethostbyname(ip_or_domain)
            logging.info(f"域名 {ip_or_domain} 解析为 IP: {ip}")
        else:
            ip = ip_or_domain
        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            flag = COUNTRY_FLAGS.get(country_code, '🏁')
            cache[ip_or_domain] = flag
            return flag
    except Exception as e:
        logging.warning(f"GeoIP 查询失败: {e}")
        return '🏁'

def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'

    if not os.path.exists(GEOIP_DB_PATH):
        logging.error(f"GeoIP 数据库文件 {GEOIP_DB_PATH} 不存在")
        return

    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies', []):
        n = parse_url_node(x) if isinstance(x, str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n:
            nodes.append(n)
    logging.info(f"加载 {len(nodes)} 个节点")

    if not nodes:
        logging.info("没有可测试的节点")
        return

    valid_nodes = test_nodes(nodes, BASE_PORT)
    
    if valid_nodes:
        for i, proxy in enumerate(valid_nodes):
            name = str(proxy['name'])
            match = re.match(r'^([\U0001F1E6-\U0001F1FF][\U0001F1E6-\U0001F1FF])', name)
            flag = match.group(1) if match else get_country_flag(proxy['server'])
            proxy['name'] = f"{flag} bing{i + 1}"
        save_yaml({'proxies': valid_nodes}, out)
        logging.info(f"有效节点数: {len(valid_nodes)}")
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
