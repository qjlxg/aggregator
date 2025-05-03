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

# 国家代码到国旗emoji的映射
COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵', 
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

def get_country_flag(ip_or_domain):
    """获取 IP 或域名对应的国家国旗"""
    try:
        # 如果是域名，先解析为 IP
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_or_domain):
            try:
                ip = socket.gethostbyname(ip_or_domain)
            except:
                return '🏁'  # 解析失败返回默认旗帜
        else:
            ip = ip_or_domain

        # 使用 GeoIP2 数据库查询国家代码
        with geoip2.database.Reader('./clash/Country.mmdb') as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            return COUNTRY_FLAGS.get(country_code, '🏁')
    except:
        return '🏁'

def format_proxy(proxy):
    """格式化代理配置为指定格式"""
    # 获取服务器的国旗
    flag = get_country_flag(proxy['server'])
    
    # 基本配置
    formatted = {
        'name': f"{flag} {proxy['name']}" if not re.match(r'^[\U0001F1E6-\U0001F1FF]{2}', proxy['name']) else proxy['name'],
        'server': proxy['server'],
        'port': proxy['port'],
        'type': proxy['type'],
        'udp': True
    }
    
    # 根据不同类型添加特定字段
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
            'cipher': proxy['cipher'],
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
    """保存为指定格式的 YAML 文件"""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write("proxies:\n")
            for proxy in data['proxies']:
                formatted_proxy = format_proxy(proxy)
                # 将代理配置转换为单行格式
                proxy_str = yaml.dump([formatted_proxy], default_flow_style=True, allow_unicode=True)
                # 删除开头的连字符和方括号
                proxy_str = proxy_str.strip('[]\n')
                f.write(f" - {proxy_str}\n")
        logging.info(f"已保存 {path}")
    except Exception as e:
        logging.error(f"保存文件失败: {e}")
