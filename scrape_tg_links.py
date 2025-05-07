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
MAX_PAGES = int(config.get('settings', 'max_pages', fallback='10')) # 提供默认值
MAX_WORKERS = int(config.get('settings', 'max_workers', fallback='5')) # 提供默认值
BASE_URL = config.get('settings', 'base_url')
TARGET_URL = config.get('settings', 'target_url', 'https://t.me/s/dingyue_center') # 目标 Telegram 频道 URL
KEYWORDS = [kw.strip() for kw in config.get('settings', 'keywords', '/api/,oken=,/s/').split(',')] # 从配置读取关键词
SCROLL_PAUSE_TIME = int(config.get('settings', 'scroll_pause_time', '3')) # 滚动暂停时间
NUM_SCROLLS = int(config.get('settings', 'num_scrolls', '10')) # 滚动次数

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

def extract_all_links_requests(html, base_url, keywords, excluded_extensions):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        absolute_url = urljoin(base_url, href)
        if absolute_url.startswith('http') and not absolute_url.startswith('https://t.me') and not absolute_url.endswith(excluded_extensions):
            for keyword in keywords:
                if keyword in absolute_url:
                    links.add(absolute_url)
                    break
    pattern = r'https?://[^\s\'"<>]+'
    for link in re.findall(pattern, html):
        if not link.startswith('https://t.me') and not link.endswith(excluded_extensions):
            for keyword in keywords:
                if keyword in link:
                    links.add(link)
                    break
    return list(links)

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

def get_next_page_url(html, current_url):
    soup = BeautifulSoup(html, 'html.parser')
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        return urljoin('https://t.me', next_page['href'])
    next_page_texts = ["下一页", "Next", ">", "»"]
    for text in next_page_texts:
        next_link = soup.find('a', string=re.compile(text))
        if next_link and 'href' in next_link.attrs:
            return urljoin(current_url, next_link['href'])
        next_link = soup.find('a', title=re.compile(text))
        if next_link and 'href' in next_link.attrs:
            return urljoin(current_url, next_link['href'])
    return None

def process_link(link):
    if test_url(link):
        try:
            with open(OUTPUT_VALID_FILE, 'a', encoding='utf-8') as f:
                f.write(link + '\n')
            logging.info(f"有效链接：{link}")
            print(f"有效链接 (控制台): {link}")
        except Exception as e:
            logging.error(f"写入有效链接文件失败 {OUTPUT_VALID_FILE}: {e}")
    else:
        try:
            with open(OUTPUT_INVALID_FILE, 'a', encoding='utf-8') as f:
                f.write(link + '\n')
            logging.info(f"无效链接：{link}")
            print(f"无效链接 (控制台): {link}")
        except Exception as e:
            logging.error(f"写入无效链接文件失败 {OUTPUT_INVALID_FILE}: {e}")

def extract_links_selenium_with_scroll(url, keywords, scroll_pause_time=2, num_scrolls=5):
    """
    使用 Selenium 抓取页面，滚动加载更多内容，并提取包含特定关键词的外部链接。
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    user_data_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f'--user-data-dir={user_data_dir}')

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.get(url)
        time.sleep(5)

        links = set()
        body = driver.find_element(By.TAG_NAME, 'body')

        for _ in range(num_scrolls):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(scroll_pause_time)
            logging.info(f"Selenium 滚动页面 {_ + 1}/{num_scrolls}")

            elements = driver.find_elements(By.TAG_NAME, 'a')
            for element in elements:
                href = element.get_attribute('href')
                if href and href.startswith('http') and not href.startswith('https://t.me'):
                    for keyword in keywords:
                        if keyword in href:
                            links.add(href)
                            break
    except Exception as e:
        logging.error(f"Selenium 滚动或链接提取过程中发生错误: {e}")
    finally:
        driver.quit()
        shutil.rmtree(user_data_dir, ignore_errors=True)

    return list(links)

def main():
    logging.info(f"DATA_DIR is: {DATA_DIR}")
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(OUTPUT_VALID_FILE):
        with open(OUTPUT_VALID_FILE, 'w') as f:
            pass
    if not os.path.exists(OUTPUT_INVALID_FILE):
        with open(OUTPUT_INVALID_FILE, 'w') as f:
            pass

    logging.info(f"开始使用 Selenium 抓取: {TARGET_URL}")
    external_links = extract_links_selenium_with_scroll(TARGET_URL, KEYWORDS, SCROLL_PAUSE_TIME, NUM_SCROLLS)
    logging.info(f"Selenium 抓取完成，找到 {len(external_links)} 个符合条件的外部链接。")
    for link in external_links:
        process_link(link)

if __name__ == '__main__':
    main()
