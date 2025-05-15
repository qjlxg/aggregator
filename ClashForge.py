# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import base64
import subprocess
import threading
import time
import urllib.parse
import json
import glob
import re
import yaml
import random
import string
import httpx
import asyncio
from itertools import chain
from typing import Dict, List, Optional
import sys
import requests
import zipfile
import gzip
import shutil
import platform
import os
import logging
from datetime import datetime
from asyncio import Semaphore
import ssl
import traceback
ssl._create_default_https_context = ssl._create_unverified_context
import warnings
warnings.filterwarnings('ignore')
from requests_html import HTMLSession

# Constants
TEST_URL = "http://www.pinterest.com"
CLASH_API_PORTS = [9090]
CLASH_API_HOST = "127.0.0.1"
CLASH_API_SECRET = ""
TIMEOUT = 1
MAX_CONCURRENT_TESTS = 100
LIMIT = 20  # Maximum number of nodes to retain
CONFIG_FILE = 'data/clash_config.yaml'
INPUT = "data"  # Directory for loading proxy nodes
BAN = ["中国", "China", "CN", "电信", "移动", "联通"]
headers = {
    'Accept-Charset': 'utf-8',
    'Accept': 'text/html,application/x-yaml,*/*',
    'User-Agent': 'Clash Verge/1.7.7'
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("clash_script.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Clash configuration template (unchanged, omitted for brevity)
clash_config_template = {...}  # Replace with the original template

# Utility Functions
def parse_proxy_link(link: str) -> Optional[Dict]:
    """Parse various proxy links with error handling."""
    parsers = {
        ("hysteria2://", "hy2://"): parse_hysteria2_link,
        "trojan://": parse_trojan_link,
        "ss://": parse_ss_link,
        "vless://": parse_vless_link,
        "vmess://": parse_vmess_link
    }
    try:
        for prefixes, parser in parsers.items():
            if isinstance(prefixes, str) and link.startswith(prefixes):
                return parser(link)
            elif isinstance(prefixes, tuple) and any(link.startswith(p) for p in prefixes):
                return parser(link)
        logger.warning(f"Unsupported proxy link: {link}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse link {link}: {e}", exc_info=True)
        return None

def deduplicate_proxies(proxies_list: List[Dict]) -> List[Dict]:
    """Remove duplicate proxies based on server, port, type, and password."""
    seen = set()
    unique_proxies = []
    for proxy in proxies_list:
        key = (proxy['server'], proxy['port'], proxy['type'], proxy.get('password', ''))
        if key not in seen:
            seen.add(key)
            unique_proxies.append(proxy)
    return unique_proxies

def add_random_suffix(name: str, existing_names: set, max_retries: int = 10) -> str:
    """Add a random suffix to resolve name conflicts."""
    for _ in range(max_retries):
        suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
        new_name = f"{name}-{suffix}"
        if new_name not in existing_names:
            return new_name
    raise ValueError(f"Could not generate unique name for {name} after {max_retries} attempts")

def read_txt_files(folder_path: str) -> List[str]:
    """Read proxy links from txt files in the specified directory."""
    try:
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        all_lines = []
        for file_path in txt_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines.extend(line.strip() for line in f.readlines())
        if all_lines:
            logger.info(f"Loaded {len(all_lines)} links from txt files in {folder_path}")
        return all_lines
    except Exception as e:
        logger.error(f"Error reading txt files from {folder_path}: {e}", exc_info=True)
        return []

def read_yaml_files(folder_path: str) -> List[Dict]:
    """Read proxy nodes from yaml/yml files in the specified directory."""
    try:
        yaml_files = glob.glob(os.path.join(folder_path, '*.yaml')) + glob.glob(os.path.join(folder_path, '*.yml'))
        load_nodes = []
        for file_path in yaml_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if config and 'proxies' in config:
                    load_nodes.extend(config['proxies'])
        if load_nodes:
            logger.info(f"Loaded {len(load_nodes)} nodes from yaml files in {folder_path}")
        return load_nodes
    except Exception as e:
        logger.error(f"Error reading yaml files from {folder_path}: {e}", exc_info=True)
        return []

def generate_clash_config(links: List[str], load_nodes: List[Dict]):
    """Generate Clash configuration with improved error handling."""
    logger.info("Generating Clash configuration")
    config = clash_config_template.copy()
    final_nodes = []
    existing_names = set()

    def resolve_name_conflicts(node: Dict):
        name = str(node["name"])
        if not_contains(name):
            if name in existing_names:
                name = add_random_suffix(name, existing_names)
            existing_names.add(name)
            node["name"] = name
            final_nodes.append(node)

    # Process loaded nodes
    for node in load_nodes:
        resolve_name_conflicts(node)

    # Process links
    for link in links:
        try:
            if link.startswith(("hysteria2://", "hy2://", "trojan://", "ss://", "vless://", "vmess://")):
                node = parse_proxy_link(link)
                if node:
                    resolve_name_conflicts(node)
            else:
                logger.info(f"Processing URL: {link}")
                new_links, is_yaml = process_url(link)
                if is_yaml:
                    for node in new_links:
                        resolve_name_conflicts(node)
                else:
                    for new_link in new_links:
                        node = parse_proxy_link(new_link)
                        if node:
                            resolve_name_conflicts(node)
        except Exception as e:
            logger.error(f"Error processing link {link}: {e}", exc_info=True)

    final_nodes = deduplicate_proxies(final_nodes)
    for node in final_nodes:
        name = node["name"]
        config["proxy-groups"][1]["proxies"].append(name)
        config["proxy-groups"][2]["proxies"].append(name)
        config["proxy-groups"][3]["proxies"].append(name)
    config["proxies"] = final_nodes

    if config["proxies"]:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"Clash configuration saved to {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}", exc_info=True)
    else:
        logger.warning("No proxy nodes to update")

def not_contains(s: str) -> bool:
    """Check if string contains banned keywords."""
    return not any(k in s for k in BAN)

# Clash API and Testing
class ClashAPI:
    """Clash API client with enhanced error handling."""
    def __init__(self, host: str, ports: List[int], secret: str = ""):
        self.host = host
        self.ports = ports
        self.base_url = None
        self.headers = {"Authorization": f"Bearer {secret}" if secret else ""}
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        self.semaphore = Semaphore(MAX_CONCURRENT_TESTS)
        self._test_results_cache: Dict[str, ProxyTestResult] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def check_connection(self) -> bool:
        """Check connection to Clash API across multiple ports."""
        for port in self.ports:
            try:
                url = f"http://{self.host}:{port}/version"
                response = await self.client.get(url)
                response.raise_for_status()
                self.base_url = f"http://{self.host}:{port}"
                logger.info(f"Connected to Clash API on port {port}")
                return True
            except httpx.RequestError as e:
                logger.warning(f"Failed to connect on port {port}: {e}")
        logger.error("Failed to connect to any Clash API port")
        return False

    async def test_proxy_delay(self, proxy_name: str) -> 'ProxyTestResult':
        """Test proxy delay with caching."""
        if proxy_name in self._test_results_cache:
            cached = self._test_results_cache[proxy_name]
            if (datetime.now() - cached.tested_time).total_seconds() < 60:
                return cached
        async with self.semaphore:
            try:
                response = await self.client.get(
                    f"{self.base_url}/proxies/{proxy_name}/delay",
                    params={"url": TEST_URL, "timeout": int(TIMEOUT * 1000)}
                )
                response.raise_for_status()
                delay = response.json().get("delay")
                result = ProxyTestResult(proxy_name, delay)
            except Exception as e:
                logger.error(f"Failed to test {proxy_name}: {e}")
                result = ProxyTestResult(proxy_name)
            self._test_results_cache[proxy_name] = result
            return result

class ProxyTestResult:
    """Proxy test result class."""
    def __init__(self, name: str, delay: Optional[float] = None):
        self.name = name
        self.delay = delay if delay is not None else float('inf')
        self.status = "ok" if delay is not None else "fail"
        self.tested_time = datetime.now()

    @property
    def is_valid(self) -> bool:
        return self.status == "ok"

def start_clash() -> subprocess.Popen:
    """Start Clash process with retry and error handling."""
    system_platform = platform.system().lower()
    clash_binary = f"./clash-{system_platform}" if system_platform in ["linux", "darwin"] else ".\\clash.exe"
    if not os.path.exists(clash_binary):
        download_and_extract_latest_release()
    if system_platform in ["linux", "darwin"]:
        os.chmod(clash_binary, 0o755)

    max_retries = 5
    for attempt in range(max_retries):
        try:
            process = subprocess.Popen(
                [clash_binary, '-f', CONFIG_FILE],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            time.sleep(5)
            if is_clash_api_running():
                logger.info("Clash started successfully")
                return process
            process.kill()
            logger.warning(f"Clash start attempt {attempt + 1}/{max_retries} failed")
        except Exception as e:
            logger.error(f"Error starting Clash: {e}", exc_info=True)
    raise RuntimeError("Failed to start Clash after multiple attempts")

def is_clash_api_running() -> bool:
    """Check if Clash API is running."""
    try:
        response = requests.get(f"http://{CLASH_API_HOST}:{CLASH_API_PORTS[0]}/configs", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

async def proxy_clean():
    """Clean proxies by testing and updating configuration."""
    logger.info("Starting proxy cleaning process")
    config = ClashConfig(CONFIG_FILE)
    async with ClashAPI(CLASH_API_HOST, CLASH_API_PORTS, CLASH_API_SECRET) as clash_api:
        if not await clash_api.check_connection():
            return
        group_name = config.get_group_names()[1]  # Test the first non-select group
        proxies = config.get_group_proxies(group_name)
        if not proxies:
            logger.warning(f"No proxies found in group {group_name}")
            return
        results = await test_group_proxies(clash_api, proxies)
        config.remove_invalid_proxies(results)
        valid_results = sorted([r for r in results if r.is_valid], key=lambda x: x.delay)[:LIMIT]
        proxy_names = {r.name for r in valid_results}
        for group in config.get_group_names()[1:]:
            config.update_group_proxies(group, valid_results)
        config.keep_proxies_by_limit(proxy_names)
        config.save()
        print_test_summary(group_name, results)

def work(links: List[str], check: bool = False, allowed_types: List[str] = [], only_check: bool = False):
    """Main workflow with error handling and process management."""
    try:
        if not only_check:
            load_nodes = read_yaml_files(INPUT)
            if allowed_types:
                load_nodes = [n for n in load_nodes if n.get('type') in allowed_types]
            links = list(chain(read_txt_files(INPUT), links))
            if links or load_nodes:
                generate_clash_config(links, load_nodes)

        if check or only_check:
            clash_process = None
            try:
                clash_process = start_clash()
                switch_proxy('DIRECT')
                asyncio.run(proxy_clean())
            finally:
                if clash_process:
                    clash_process.terminate()
                    clash_process.wait()
                    logger.info("Clash process terminated")
    except KeyboardInterrupt:
        logger.info("User interrupted execution")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Program execution failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    links = []
    work(links, check=True, only_check=False, allowed_types=["ss", "hysteria2", "hy2", "vless", "vmess", "trojan"])
