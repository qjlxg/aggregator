
import os
import re
import requests
from bs4 import BeautifulSoup
import time
import logging
import concurrent.futures
import configparser

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 读取配置
config = configparser.ConfigParser()
config.read('config.ini')

BASE_URL = config.get('settings', 'base_url')
DATA_DIR = config.get('settings', 'data_dir')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_valid_file'))
OUTPUT_INVALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_invalid_file'))
MAX_PAGES = int(config.get('settings', 'max_pages'))
MAX_WORKERS = int(config.get('settings', 'max_workers'))

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logging.error(f"请求失败 {url}: {e}")
        return None

def extract_all_links(html):
    pattern = r'https?://[^\s\'"<>]+'
    all_links = re.findall(pattern, html)
    filtered_links = [link for link in all_links if not link.startswith('https://t.me')]
    return filtered_links

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

def get_next_page_url(html, current_url):
    soup = BeautifulSoup(html, 'html.parser')
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        return 'https://t.me' + next_page['href']
    return None

def process_link(link):
    if link.startswith('https://t.me'):
        logging.info(f"跳过t.me链接：{link}")
        return
    if test_url(link):
        with open(OUTPUT_VALID_FILE, 'a', encoding='utf-8') as f:
            f.write(link + '\n')
        logging.info(f"有效链接：{link}")
    else:
        with open(OUTPUT_INVALID_FILE, 'a', encoding='utf-8') as f:
            f.write(link + '\n')
        logging.info(f"无效链接：{link}")

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    # 如果文件不存在，则创建空文件
    if not os.path.exists(OUTPUT_VALID_FILE):
        with open(OUTPUT_VALID_FILE, 'w') as f:
            pass
    if not os.path.exists(OUTPUT_INVALID_FILE):
        with open(OUTPUT_INVALID_FILE, 'w') as f:
            pass

    current_url = BASE_URL
    collected_links = set()
    page_count = 0

    while current_url and page_count < MAX_PAGES:
        logging.info(f"抓取页面：{current_url}")
        html = fetch_page(current_url)
        if not html:
            break

        links = extract_all_links(html)
        logging.info(f"找到 {len(links)} 个非t.me链接。")

        new_links = [link for link in links if link not in collected_links]
        collected_links.update(new_links)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            executor.map(process_link, new_links)

        current_url = get_next_page_url(html, current_url)
        page_count += 1
        time.sleep(1)

    logging.info(f"全部完成，共抓取到 {len(collected_links)} 个非t.me链接。")

if __name__ == '__main__':
    main()
