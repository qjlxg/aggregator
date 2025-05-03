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

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量
BASE_PORT = 10000
TEST_URLS = ["https://www.google.com", "https://www.youtube.com"]
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']
MAX_WORKERS = 20
REQUEST_TIMEOUT = 10
STARTUP_DELAY = 2

# 定义每种代理类型的字段顺序
FIELD_ORDERS = {
    'vmess': ['name', 'server', 'port', 'type', 'uuid', 'alterId', 'cipher', 'tls', 'network', 'ws-opts', 'udp'],
    'ss': ['name', 'server', 'port', 'type', 'cipher', 'password', 'udp'],
    'hysteria2': ['name', 'server', 'port', 'type', 'password', 'auth', 'sni', 'skip-cert-verify', 'udp'],
    'trojan': ['name', 'server', 'port', 'type', 'password', 'sni', 'skip-cert-verify', 'udp'],
    'vless': ['name', 'server', 'port', 'type', 'uuid', 'tls', 'servername', 'network', 'reality-opts', 'client-fingerprint', 'udp']
}

# 自定义 YAML Dumper 用于固定字段顺序和横排格式
class CustomDumper(yaml.Dumper):
    def represent_mapping(self, tag, mapping, flow_style=None):
        if isinstance(mapping, dict) and 'name' in mapping and 'server' in mapping:
            proxy_type = mapping.get('type', 'ss')
            order = FIELD_ORDERS.get(proxy_type, ['name', 'server', 'port', 'type'])
            ordered_mapping = {key: mapping[key] for key in order if key in mapping}
            return super().represent_mapping(tag, ordered_mapping, flow_style=True)
        else:
            return super().represent_mapping(tag, mapping, flow_style=False)

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, Dumper=CustomDumper, allow_unicode=True)
    logging.info(f"已保存 {path}")

def parse_url_node(url):
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
                'name': urllib.parse.unquote
