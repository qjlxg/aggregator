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

# 常量定义
BASE_PORT = 10000
TEST_URLS = ["https://www.google.com", "https://www.youtube.com"]
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 20
REQUEST_TIMEOUT = 10
STARTUP_DELAY = 2
GEOIP_DB_PATH = './clash/Country.mmdb'

# 国家代码到国旗emoji的映射
COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵', 
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

# 字段顺序定义
FIELD_ORDERS = {
    'vmess': ['name', 'server', 'port', 'type', 'uuid', 'alterId', 'cipher', 'tls', 'network', 'ws-opts', 'udp'],
    'ss': ['name', 'server', 'port', 'type', 'cipher', 'password', 'udp'],
    'hysteria2': ['name', 'server', 'port', 'type', 'password', 'auth', 'sni', 'skip-cert-verify', 'udp'],
    'trojan': ['name', 'server', 'port', 'type', 'password', 'sni', 'skip-cert-verify', 'udp'],
    'vless': ['name', 'server', 'port', 'type', 'uuid', 'tls', 'servername', 'network', 'udp']
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

def get_country_flag(ip_or_domain):
    try:
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_or_domain):
            try:
                ip = socket.gethostbyname(ip_or_domain)
                logging.info(f"域名 {ip_or_domain} 解析为 IP: {ip}")
            except Exception as e:
                logging.warning(f"域名解析失败: {e}")
                return '🏁'
        else:
            ip = ip_or_domain
        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            return COUNTRY_FLAGS.get(country_code, '🏁')
    except Exception as e:
        logging.warning(f"GeoIP 查询失败: {e}")
        return '🏁'

def format_proxy(proxy):
    flag = get_country_flag(proxy['server'])
    formatted = {
        'name': f"{flag} {proxy['name']}" if not re.match(r'^[\U0001F1E6-\U0001F1FF]{2}', proxy['name']) else proxy['name'],
        'server': proxy['server'],
        'port': proxy['port'],
        'type': proxy['type'],
        'udp': True
    }
    if proxy['type'] == 'vmess':
        formatted.update({
            'uuid': proxy['uuid'],
            'alterId': proxy.get('alterId', 0),
            'cipher': proxy.get('cipher', 'auto'),
            'tls': proxy.get('tls', False),
        })
        if proxy.get('network') == 'ws':
            formatted['network'] = 'ws'
            formatted['ws-opts'] = proxy.get('ws-opts', {'path': '/'})
    elif proxy['type'] == 'ss':
        formatted.update({
            'cipher': proxy.get('cipher', 'chacha20-ietf-poly1305'),
            'password': proxy['password']
        })
    elif proxy['type'] == 'trojan':
        formatted.update({
            'password': proxy['password'],
            'sni': proxy.get('sni', ''),
            'skip-cert-verify': False
        })
    elif proxy['type'] == 'hysteria2':
        formatted.update({
            'password': proxy['password'],
            'auth': proxy.get('auth', proxy['password']),
            'sni': proxy.get('sni', proxy['server']),
            'skip-cert-verify': False
        })
    elif proxy['type'] == 'vless':
        formatted.update({
            'uuid': proxy['uuid'],
            'tls': True,
            'servername': proxy.get('servername', proxy['server'])
        })
    return formatted

def save_yaml(data, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write("proxies:\n")
            for proxy in data['proxies']:
                formatted_proxy = format_proxy(proxy)
                proxy_str = yaml.dump([formatted_proxy], Dumper=CustomDumper, allow_unicode=True)
                proxy_str = proxy_str.strip('[]\n')
                f.write(f" - {proxy_str}\n")
        logging.info(f"已保存 {path}")
    except Exception as e:
        logging.error(f"保存文件失败: {e}")

# 示例主函数（基于历史代码）
def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'
    if not os.path.exists(GEOIP_DB_PATH):
        logging.error(f"GeoIP 数据库文件 {GEOIP_DB_PATH} 不存在")
        return
    d = {'proxies': [
        {'name': 'proxy1', 'server': 'example.com', 'port': 1234, 'type': 'ss', 'cipher': 'aes-128-gcm', 'password': 'pass'},
        {'name': '🇺🇸 proxy2', 'server': '192.168.1.1', 'port': 5678, 'type': 'vmess', 'uuid': 'uuid'}
    ]}
    save_yaml(d, out)

if __name__ == "__main__":
    main()
