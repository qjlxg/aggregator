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
import re
import socket
import geoip2.database

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量
BASE_PORT = 10000
TEST_URLS = ["https://www.google.com", "https://www.youtube.com"]
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 10  # 减少并发，防止资源耗尽
REQUEST_TIMEOUT = 5  # 缩短超时时间，提高效率
STARTUP_DELAY = 3  # 增加启动延迟，确保 Clash 就绪
GEOIP_DB_PATH = './clash/Country.mmdb'
CLASH_PATH = './clash/clash-linux'  # Clash 可执行文件路径

# 国家代码到国旗 emoji 的映射
COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵',
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

# 定义每种代理类型的字段顺序
FIELD_ORDERS = {
    'vmess': ['name', 'server', 'port', 'type', 'uuid', 'alterId', 'cipher', 'tls', 'network', 'ws-opts', 'udp'],
    'ss': ['name', 'server', 'port', 'type', 'cipher', 'password', 'udp'],
    'hysteria2': ['name', 'server', 'port', 'type', 'password', 'auth', 'sni', 'skip-cert-verify', 'udp'],
    'trojan': ['name', 'server', 'port', 'type', 'password', 'sni', 'skip-cert-verify', 'udp'],
    'vless': ['name', 'server', 'port', 'type', 'uuid', 'tls', 'servername', 'network', 'reality-opts', 'client-fingerprint', 'udp']
}

# 自定义 YAML Dumper
class CustomDumper(yaml.Dumper):
    def represent_mapping(self, tag, mapping, flow_style=None):
        if isinstance(mapping, dict) and 'name' in mapping and 'server' in mapping:
            proxy_type = mapping.get('type', 'ss')
            order = FIELD_ORDERS.get(proxy_type, ['name', 'server', 'port', 'type'])
            ordered_mapping = {key: mapping[key] for key in order if key in mapping}
            return super().represent_mapping(tag, ordered_mapping, flow_style=True)
        return super().represent_mapping(tag, mapping, flow_style=False)

def load_yaml(path):
    """加载 YAML 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    """保存代理配置为单行 YAML 格式"""
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
    """解析代理 URL 节点"""
    try:
        if url.startswith('vmess://'):
            data = json.loads(base64.b64decode(url[8:]).decode())
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
            method_pass = base64.b64decode(parsed.netloc.split('@')[0]).decode()
            method, passwd = method_pass.split(':')
            server, port = parsed.netloc.split('@')[1].split(':')
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

def start_clash(node, port):
    """启动 Clash 实例测试节点"""
    if not os.path.isfile(CLASH_PATH) or not os.access(CLASH_PATH, os.X_OK):
        logging.error(f"Clash 可执行文件 {CLASH_PATH} 不存在或不可执行")
        return None, None
    cfg = {
        'port': port,
        'socks-port': port + 1,
        'mode': 'global',
        'proxies': [node],
        'proxy-groups': [{'name': 'Proxy', 'type': 'select', 'proxies': [node['name']]}],
        'rules': ['MATCH,Proxy']
    }
    fname = f'temp_{port}.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True)
    try:
        p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        time.sleep(STARTUP_DELAY)
        if p.poll() is not None:  # 检查进程是否已退出
            err = p.stderr.read().decode()
            logging.error(f"Clash 启动失败: {err}")
            return None, fname
        return p, fname
    except Exception as e:
        logging.error(f"启动 Clash 失败: {e}")
        return None, fname

def stop_clash(p, fname):
    """停止 Clash 实例并清理临时文件"""
    if p:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            p.wait(timeout=2)  # 等待进程结束
        except Exception as e:
            logging.warning(f"停止 Clash 失败: {e}")
    if fname and os.path.exists(fname):
        os.remove(fname)

def test_node(node, idx):
    """测试节点是否可用"""
    port = BASE_PORT + (idx % 100) * 2
    logging.info(f"测试节点: {node['name']} (端口: {port})")
    p, cfg = start_clash(node, port)
    if not p:
        logging.error(f"节点 {node['name']} 测试失败: Clash 未启动")
        stop_clash(p, cfg)
        return None

    # 获取本地 IP（不使用代理）
    try:
        local_ip = requests.get("https://api.ipify.org", timeout=5).text
    except Exception:
        local_ip = "未知"

    # 通过代理测试
    proxies = {'http': f'socks5://127.0.0.1:{port + 1}', 'https': f'socks5://127.0.0.1:{port + 1}'}
    for url in TEST_URLS:
        try:
            r = requests.get(url, proxies=proxies, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                logging.info(f"节点 {node['name']} 测试失败: {url} 返回 {r.status_code}")
                stop_clash(p, cfg)
                return None
            proxy_ip = requests.get("https://api.ipify.org", proxies=proxies, timeout=5).text
            if proxy_ip == local_ip:
                logging.info(f"节点 {node['name']} 测试失败: 代理未生效 (IP 未变化)")
                stop_clash(p, cfg)
                return None
        except Exception as e:
            logging.info(f"节点 {node['name']} 测试失败: {url} - {e}")
            stop_clash(p, cfg)
            return None

    logging.info(f"节点 {node['name']} 测试成功")
    stop_clash(p, cfg)
    return node

def get_country_flag(ip_or_domain):
    """根据 IP 或域名获取国旗 emoji"""
    try:
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_or_domain):
            ip = socket.gethostbyname(ip_or_domain)
            logging.info(f"域名 {ip_or_domain} 解析为 IP: {ip}")
        else:
            ip = ip_or_domain
        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            return COUNTRY_FLAGS.get(country_code, '🏁')
    except Exception as e:
        logging.warning(f"GeoIP 查询失败: {e}")
        return '🏁'

def main():
    """主函数：处理代理节点并生成 YAML 文件"""
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

    valid = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(test_node, node, idx) for idx, node in enumerate(nodes)]
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid.append(result)

    if valid:
        for i, proxy in enumerate(valid):
            name = str(proxy['name'])
            match = re.match(r'^([\U0001F1E6-\U0001F1FF][\U0001F1E6-\U0001F1FF])', name)
            flag = match.group(1) if match else get_country_flag(proxy['server'])
            proxy['name'] = f"{flag} bing{i + 1}"
        save_yaml({'proxies': valid}, out)
        logging.info(f"有效节点数: {len(valid)}")
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
