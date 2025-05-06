import os
import re
import requests
from bs4 import BeautifulSoup
import time
import logging
import concurrent.futures
import configparser
from urllib.parse import urljoin

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

def extract_all_links(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    keywords = ['/api/', 'oken=', '/s/']
    excluded_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.xml', '.css', '.js')

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        absolute_url = urljoin(base_url, href)
        if absolute_url.startswith('http') and not absolute_url.startswith('https://t.me') and not absolute_url.endswith(excluded_extensions):
            for keyword in keywords:
                if keyword in absolute_url:
                    links.add(absolute_url)
                    break

    # 尝试使用更宽松的正则匹配补充提取，并检查关键词和排除后缀
    pattern = r'https?://[^\s\'"<>]+'
    for link in re.findall(pattern, html):
        if not link.startswith('https://t.me') and not link.endswith(excluded_extensions):
            for keyword in keywords:
                if keyword in link:
                    links.add(link)
                    break

    # 进一步改进正则匹配，更精确匹配目标URL模式
    pattern = r'https?://[^\s\'"<>]*(/api/[^\s\'"<>]*\??[^\s\'"<>]*|oken=[^\s\'"<>]*\??[^\s\'"<>]*|/s/[^\s\'"<>]*)'
    for link in re.findall(pattern, html):
        if not link.startswith('https://t.me') and not link.endswith(excluded_extensions):
          links.add(link)

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
    # 优先查找 data-nav="next" 的链接
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        return urljoin('https://t.me', next_page['href'])

    # 尝试查找包含特定文本的 "下一页" 链接
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

def main():
    logging.info(f"DATA_DIR is: {DATA_DIR}") # 添加这行
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

        links = extract_all_links(html, current_url)
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
