import os
import requests
import base64
import yaml
import re
import asyncio
import aiohttp
import logging
from pathlib import Path
from datetime import datetime
import pytz

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从环境变量获取目标URL和GitHub Token
TARGET_URL = os.getenv('TARGET_GITHUB_URL')
if not TARGET_URL:
    raise ValueError("Environment variable TARGET_GITHUB_URL is not set")
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    raise ValueError("Environment variable GITHUB_TOKEN is not set")

# 本地保存路径
LOCAL_FILE_PATH = Path('data/hy2.txt')

# 支持的代理节点协议
SUPPORTED_PROTOCOLS = [
    'ss://',      # Shadowsocks
    'vless://',   # VLESS
    'vmess://',   # VMess
    'trojan://',  # Trojan
    'hysteria://',# Hysteria
    'tuic://',    # TUIC
]

# GitHub API搜索关键词
SEARCH_QUERIES = [
    'proxy node in:file',
    'ss:// in:file',
    'vless:// in:file',
    'vmess:// in:file',
    'trojan:// in:file',
    'hysteria:// in:file',
    'tuic:// in:file',
    'free proxy in:file',
]

# 获取当前上海时间
def get_cst_timestamp():
    cst = pytz.timezone('Asia/Shanghai')
    return datetime.now(cst).strftime('%Y-%m-%d %H:%M:%S %Z')

# 异步测试节点连通性
async def test_node_connectivity(session, url, timeout=5):
    try:
        async with session.head(url, timeout=timeout) as response:
            return response.status == 200
    except Exception as e:
        logger.debug(f"Failed to connect to {url}: {e}")
        return False

# 解码Base64格式的节点
def decode_base64_node(encoded):
    try:
        decoded = base64.b64decode(encoded).decode('utf-8')
        return decoded if any(proto in decoded for proto in SUPPORTED_PROTOCOLS) else None
    except Exception:
        return None

# 解析YAML格式的节点
def parse_yaml_nodes(content):
    try:
        data = yaml.safe_load(content)
        nodes = []
        if isinstance(data, dict) and 'proxies' in data:
            for proxy in data['proxies']:
                if 'server' in proxy and 'port' in proxy:
                    node_type = proxy.get('type', 'ss')
                    if node_type in [p.strip('://') for p in SUPPORTED_PROTOCOLS]:
                        node = f"{node_type}://{proxy['server']}:{proxy['port']}"
                        nodes.append(node)
        return nodes
    except Exception as e:
        logger.debug(f"Failed to parse YAML: {e}")
        return []

# 提取节点链接
def extract_nodes(content):
    nodes = []
    
    # 提取明文节点
    for proto in SUPPORTED_PROTOCOLS:
        pattern = rf'({proto}[^\s<>"\'{{}}]+)'
        nodes.extend(re.findall(pattern, content, re.IGNORECASE))
    
    # 尝试提取Base64编码的节点
    base64_pattern = r'([A-Za-z0-9+/=]{20,})'
    for encoded in re.findall(base64_pattern, content):
        decoded = decode_base64_node(encoded)
        if decoded:
            nodes.append(decoded)
    
    # 尝试解析YAML格式
    yaml_nodes = parse_yaml_nodes(content)
    nodes.extend(yaml_nodes)
    
    return nodes

# 保存到本地文件，带时间戳
def save_to_local(nodes):
    try:
        # 确保data目录存在
        LOCAL_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有节点和时间戳
        existing_nodes = {}
        if LOCAL_FILE_PATH.exists():
            with open(LOCAL_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if '#' in line:
                        node, timestamp = line.rsplit('#', 1)
                        existing_nodes[node.strip()] = timestamp.strip()
        
        # 当前时间戳
        current_timestamp = get_cst_timestamp()
        
        # 合并新节点，仅保留新节点或更新时间戳
        new_nodes = {}
        for node in nodes:
            if node not in existing_nodes:
                new_nodes[node] = current_timestamp
            else:
                new_nodes[node] = existing_nodes[node]  # 保留旧时间戳
        
        # 检查是否有更新
        if new_nodes == existing_nodes:
            logger.info("No new or updated nodes found, skipping save")
            return False
        
        # 保存到文件
        with open(LOCAL_FILE_PATH, 'w', encoding='utf-8') as f:
            for node, timestamp in new_nodes.items():
                f.write(f"{node} # {timestamp}\n")
        logger.info(f"Successfully saved {len(new_nodes)} nodes to {LOCAL_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to save to {LOCAL_FILE_PATH}: {e}")
        return False

async def main():
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    all_nodes = set()
    
    # 搜索GitHub
    for query in SEARCH_QUERIES:
        logger.info(f"Searching for: {query}")
        url = f"https://api.github.com/search/code?q={query}&per_page=100"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            results = response.json().get('items', [])
            
            for item in results:
                raw_url = item['html_url'].replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                try:
                    raw_response = requests.get(raw_url)
                    raw_response.raise_for_status()
                    content = raw_response.text
                    nodes = extract_nodes(content)
                    all_nodes.update(nodes)
                    logger.info(f"Found {len(nodes)} nodes in {raw_url}")
                except Exception as e:
                    logger.debug(f"Failed to fetch {raw_url}: {e}")
        except Exception as e:
            logger.error(f"Search failed for query {query}: {e}")
    
    # 测试连通性
    valid_nodes = []
    async with aiohttp.ClientSession() as session:
        tasks = [test_node_connectivity(session, node) for node in all_nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for node, result in zip(all_nodes, results):
            if result is True:
                valid_nodes.append(node)
                logger.info(f"Valid node: {node}")
    
    # 保存到本地
    if valid_nodes:
        updated = save_to_local(valid_nodes)
        if not updated:
            logger.info("No changes to commit")
    else:
        logger.info("No valid nodes found")

if __name__ == "__main__":
    asyncio.run(main())
