# -*- coding: utf-8 -*-
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
from datetime import datetime
from asyncio import Semaphore
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# Constants
TEST_URL = "http://www.pinterest.com"
CLASH_API_PORTS = [9090]
CLASH_API_HOST = "127.0.0.1"
CLASH_API_SECRET = ""
TIMEOUT = 5
MAX_CONCURRENT_TESTS = 18
LIMIT = 286
CONFIG_FILE = 'data/clash_config.yaml'
INPUT = "input"
BAN = ["中国", "China", "CN", "电信", "移动", "联通"]
HEADERS = {
    'Accept-Charset': 'utf-8',
    'Accept': 'text/html,application/x-yaml,*/*',
    'User-Agent': 'Clash Verge/1.7.7'
}

# Clash Configuration Template
CLASH_CONFIG_TEMPLATE = {
    "port": 7890,
    "socks-port": 7891,
    "redir-port": 7892,
    "allow-lan": True,
    "mode": "rule",
    "log-level": "info",
    "external-controller": "127.0.0.1:9090",
    "geodata-mode": True,
    "dns": {
        "enable": True,
        "ipv6": False,
        "default-nameserver": ["223.5.5.5", "119.29.29.29"],
        # Other configurations...
    },
    "proxies": [],
    "proxy-groups": [
        # Other groups...
    ],
    "rules": [
        # Other rules...
    ]
}

def parse_hysteria2_link(link):
    # Parsing logic remains unchanged
    ...

def parse_ss_link(link):
    # Parsing logic remains unchanged
    ...

def parse_trojan_link(link):
    # Parsing logic remains unchanged
    ...

def parse_vless_link(link):
    # Parsing logic remains unchanged
    ...

def parse_vmess_link(link):
    # Parsing logic remains unchanged
    ...

def parse_ss_sub(link):
    # Parsing logic remains unchanged
    ...

def parse_md_link(link):
    # Parsing logic remains unchanged
    ...

def js_render(url):
    timeout = 4
    browser_args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--disable-software-rasterizer', '--disable-setuid-sandbox']
    session = HTMLSession(browser_args=browser_args)
    r = session.get(f'{url}', headers=HEADERS, timeout=timeout, verify=False)
    r.html.render(timeout=timeout)
    return r

def match_nodes(text):
    # Matching logic remains unchanged
    ...

def process_url(url):
    # Processing logic remains unchanged
    ...

def parse_proxy_link(link):
    # Parsing logic remains unchanged
    ...

def deduplicate_proxies(proxies_list):
    # Deduplication logic remains unchanged
    ...

def add_random_suffix(name, existing_names):
    # Suffix addition logic remains unchanged
    ...

def read_txt_files(folder_path):
    all_lines = []
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    for file_path in txt_files:
        with open(file_path, 'r', encoding='utf-8') as file:
            all_lines.extend(line.strip() for line in file.readlines())
    return all_lines

def read_yaml_files(folder_path):
    load_nodes = []
    yaml_files = glob.glob(os.path.join(folder_path, '*.yaml')) + glob.glob(os.path.join(folder_path, '*.yml'))
    for file_path in yaml_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                if "proxies" in config:
                    load_nodes.extend(config["proxies"])
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    return load_nodes

def filter_by_types_alt(allowed_types, nodes):
    return [x for x in nodes if x.get('type') in allowed_types]

def merge_lists(*lists):
    return [item for item in chain.from_iterable(lists) if item != '']

def handle_links(new_links, resolve_name_conflicts):
    for new_link in new_links:
        if new_link.startswith(("hysteria2://", "trojan://", "ss://", "vless://", "vmess://")):
            node = parse_proxy_link(new_link)
            if node:
                resolve_name_conflicts(node)
        else:
            print(f"跳过无效或不支持的链接: {new_link}")

def generate_clash_config(links, load_nodes):
    now = datetime.now()
    final_nodes = []
    existing_names = set()
    config = CLASH_CONFIG_TEMPLATE.copy()

    def resolve_name_conflicts(node):
        # Name resolution logic remains unchanged
        ...

    for node in load_nodes:
        resolve_name_conflicts(node)

    for link in links:
        # Link processing remains unchanged
        ...

    final_nodes = deduplicate_proxies(final_nodes)

    for node in final_nodes:
        name = str(node["name"])
        if not_contains(name):
            config["proxy-groups"][1]["proxies"].append(name)
            config["proxy-groups"][2]["proxies"].append(name)
            config["proxy-groups"][3]["proxies"].append(name)

    config["proxies"] = final_nodes
    if config["proxies"]:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        with open(f'{CONFIG_FILE}.json', "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)
        print(f"已生成Clash配置文件{CONFIG_FILE}|{CONFIG_FILE}.json")
    else:
        print('没有节点数据更新')

def not_contains(s):
    return not any(k in s for k in BAN)

class ClashAPIException(Exception):
    """Custom exception for Clash API errors."""
    pass

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

def ensure_executable(file_path):
    """Ensure file has executable permissions."""
    if platform.system().lower() in ['linux', 'darwin']:
        os.chmod(file_path, 0o755)

def handle_clash_error(error_message, config_file_path):
    """Handle and fix Clash configuration errors."""
    # Error handling logic remains unchanged
    ...

def download_and_extract_latest_release():
    """Download and extract the latest release of Mihomo."""
    # Download logic remains unchanged
    ...

def read_output(pipe, output_lines):
    """Read output from subprocess pipe."""
    while True:
        line = pipe.readline()
        if line:
            output_lines.append(line)
        else:
            break

def start_clash():
    """Start the Clash process."""
    download_and_extract_latest_release()
    system_platform = platform.system().lower()
    clash_binary = './clash' if system_platform in ['linux', 'darwin'] else './clash.exe'
    ensure_executable(clash_binary)

    while True:
        clash_process = subprocess.Popen(
            [clash_binary, '-f', CONFIG_FILE],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )

        output_lines = []
        stdout_thread = threading.Thread(target=read_output, args=(clash_process.stdout, output_lines))
        stdout_thread.start()

        timeout = 3
        start_time = time.time()
        while time.time() - start_time < timeout:
            stdout_thread.join(timeout=0.5)
            if output_lines:
                if 'GeoIP.dat' in output_lines[-1]:
                    print(output_lines[-1])
                    time.sleep(5)
                    if is_clash_api_running():
                        return clash_process

                if "Parse config error" in output_lines[-1]:
                    if handle_clash_error(output_lines[-1], CONFIG_FILE):
                        clash_process.kill()
                        output_lines = []
            if is_clash_api_running():
                return clash_process

def is_clash_api_running() -> bool:
    """Check if Clash API is running."""
    try:
        url = f"http://{CLASH_API_HOST}:{CLASH_API_PORTS[0]}/configs"
        response = requests.get(url)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def switch_proxy(proxy_name='DIRECT'):
    """Switch proxy in Clash."""
    url = f"http://{CLASH_API_HOST}:{CLASH_API_PORTS[0]}/proxies/节点选择"
    data = {"name": proxy_name}

    try:
        response = requests.put(url, json=data)
        if response.status_code == 204:
            print(f"切换到 '节点选择-{proxy_name}' successful.")
            return {"status": "success", "message": f"Switched to proxy '{proxy_name}'."}
        else:
            return response.json()
    except Exception as e:
        print(f"Error occurred: {e}")
        return {"status": "error", "message": str(e)}

class ClashAPI:
    def __init__(self, host: str, ports: List[int], secret: str = ""):
        # Initialization logic remains unchanged
        ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def check_connection(self) -> bool:
        """Check connection status with Clash API."""
        for port in self.ports:
            try:
                test_url = f"http://{self.host}:{port}"
                response = await self.client.get(f"{test_url}/version")
                if response.status_code == 200:
                    version = response.json().get('version', 'unknown')
                    print(f"成功连接到 Clash API (端口 {port})，版本: {version}")
                    self.base_url = test_url
                    return True
            except httpx.RequestError:
                continue
        print("所有端口均连接失败")
        return False

    async def get_proxies(self) -> Dict:
        """Get all proxy information."""
        if not self.base_url:
            raise ClashAPIException("未建立与 Clash API 的连接")

        try:
            response = await self.client.get(f"{self.base_url}/proxies", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("认证失败，请检查 API Secret 是否正确")
            raise ClashAPIException(f"HTTP 错误: {e}")

    async def test_proxy_delay(self, proxy_name: str) -> ProxyTestResult:
        """Test the delay of a specified proxy."""
        if not self.base_url:
            raise ClashAPIException("未建立与 Clash API 的连接")

        async with self.semaphore:
            try:
                response = await self.client.get(
                    f"{self.base_url}/proxies/{proxy_name}/delay",
                    headers=self.headers,
                    params={"url": TEST_URL, "timeout": int(TIMEOUT * 1000)}
                )
                response.raise_for_status()
                delay = response.json().get("delay")
                return ProxyTestResult(proxy_name, delay)
            except httpx.HTTPError:
                return ProxyTestResult(proxy_name)

async def test_group_proxies(clash_api: ClashAPI, proxies: List[str]) -> List[ProxyTestResult]:
    """Test a group of proxies."""
    # Testing logic remains unchanged
    ...

async def proxy_clean():
    """Perform proxy cleaning."""
    # Cleaning logic remains unchanged
    ...

def work(links, check=False, allowed_types=[], only_check=False):
    """Main function to handle the work."""
    try:
        if not only_check:
            load_nodes = read_yaml_files(folder_path=INPUT)
            if allowed_types:
                load_nodes = filter_by_types_alt(allowed_types, load_nodes)
            links = merge_lists(read_txt_files(folder_path=INPUT), links)
            if links or load_nodes:
                generate_clash_config(links, load_nodes)

        if check or only_check:
            clash_process = None
            try:
                print(f"===================启动clash并初始化配置======================")
                clash_process = start_clash()
                switch_proxy('DIRECT')
                asyncio.run(proxy_clean())
                print(f'批量检测完毕')
            except Exception as e:
                print("Error calling Clash API:", e)
            finally:
                print(f'关闭Clash API')
                if clash_process:
                    clash_process.kill()

    except KeyboardInterrupt:
        print("\n用户中断执行")
        sys.exit(0)
    except Exception as e:
        print(f"程序执行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    links = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.yaml",
        # Other URLs...
    ]
    work(links, check=True, only_check=False, allowed_types=["ss", "hysteria2", "hy2", "vless", "vmess", "trojan"])
