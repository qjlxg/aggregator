import os
import re
import requests
from bs4 import BeautifulSoup
import time
import logging
import concurrent.futures
import configparser
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import tempfile
import shutil

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 读取配置
config = configparser.ConfigParser()
config.read('config.ini')

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', '.') # 获取 GitHub 工作区路径，默认为当前目录
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_valid_file', fallback='valid_links.txt'))
OUTPUT_INVALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_invalid_file', fallback='invalid_links.txt'))
MAX_PAGES = int(config.get('settings', 'max_pages', fallback='1')) # Selenium 方式通常不需要大量翻页
MAX_WORKERS = int(config.get('settings', 'max_workers', fallback='5'))
BASE_URL = config.get('settings', 'base_url', fallback='') # 可以设置一个默认的 base_url
TARGET_URL = config.get('settings', 'target_url', fallback='https://t.me/s/dingyue_center') # 目标 Telegram 频道 URL
SCROLL_PAUSE_TIME = int(config.get('settings', 'scroll_pause_time', fallback='3')) # 滚动暂停时间
NUM_SCROLLS = int(config.get('settings', 'num_scrolls', fallback='10')) # 滚动次数

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"请求失败 {url}: {e}")
        return None

def extract_all_links_requests(html, base_url, excluded_extensions):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        absolute_url = urljoin(base_url, href)
        if absolute_url.startswith('http') and not absolute_url.startswith('https://t.me') and not absolute_url.endswith(excluded_extensions) and 'telegram' not in absolute_url.lower():
            links.add(absolute_url)
    pattern = r'https?://[^\s\'"<>]+'
    for link in re.findall(pattern, html):
        if not link.startswith('https://t.me') and not link.endswith(excluded_extensions) and 'telegram' not in link.lower():
            links.add(link)
    return list(links)

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

def get
