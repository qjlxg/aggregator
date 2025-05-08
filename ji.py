import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue
from urllib.parse import urlparse
import base64

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 请求头池 (Updated with more diverse User-Agents )
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36', #added
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0', #added
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0',#added
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0' #added
]

# Constants
GITHUB_CONFIG_URL_ENCODED = "aHR0cHM6Ly9naXRodWIuY29tL3FqbHhnLzM2Mi9yYXcvcmVmcy9oZWFkcy9tYWluL2RhdGEvY29uZmlnLnR4dA=="  # Base64 encoded
GITHUB_SUBSCRIBES_URL_ENCODED = "aHR0cHM6Ly9naXRodWIuY29tL3FqbHhnLzM2Mi9yYXcvcmVmcy9oZWFkcy9tYWluL2RhdGEvc3Vic2NyaWJlcy50eHQ=" # Base64 encoded
CONFIG_URL_DECODED = base64.b64decode(GITHUB_CONFIG_URL_ENCODED).decode('utf-8')
SUBSCRIBES_URL_DECODED = base64.b64decode(GITHUB_SUBSCRIBES_URL_ENCODED).decode('utf-8') #add

def get_random_headers():
    """获取随机请求头"""
    return {'User-Agent': random.choice(USER_AGENTS)}

def is_valid_url(url):
    """判断URL是否有效"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
    """从HTML中提取URL"""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text', 'tgme_widget_message_photo',
        'tgme_widget_message_video', 'tgme_widget_message_document',
        'tgme_widget_message_poll'
    ])
    urls = set()
    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        urls.update(url for url in found_urls if is_valid_url(url))
    return list(urls)

def test_url_connectivity(url, timeout=5):
    """测试URL是否可连通"""
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} 连接测试失败: {e}")
        return False

def get_next_page_url(html):
    """提取下一页URL"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    return 'https://t.me' + load_more['href'] if load_more else None

def fetch_page(url, headers, timeout=10, max_retries=3):
    """抓取页面内容，带重试机制"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout) # Removed proxies
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.warning(f"抓取 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(38, 53))
            else:
                logging.error(f"抓取 {url} 失败，超出最大重试次数")
                return None


def append_urls_to_github(urls, github_url):
    """将 URL 追加保存到 GitHub 文件"""
    try:
        # 获取文件内容
        response = requests.get(github_url)
        response.raise_for_status()
        existing_content = response.text

        # 追加 URL (去重)
        existing_urls = set(existing_content.splitlines())
        new_urls = set(urls) - existing_urls
        updated_content = existing_content + "\n" + "\n".join(new_urls)

        # 将 content 再次上传到 GitHub (这里只是模拟. 上传需要 GitHub API 认证，这里省略)
        # Real implementation would involve using GitHub API to update the file.
        # For demonstration, we just print the content to be uploaded.
        logging.info(f"Content to be appended to {github_url}:\n{updated_content}")
        print(f"Content to be appended to {github_url}:\n{updated_content}")  # for actual use replace this line with GitHub API calls
        return updated_content #return the updated content to write file locally.
    except requests.RequestException as e:
        logging.error(f"追加到 {github_url} 失败: {e}")
        return None

def save_urls_to_file(urls, filename='data/ji.txt'):
    """保存URL到文件"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        logging.info(f"URL 已保存到 {filename}")
    except IOError as e:
        logging.error(f"保存 {filename} 失败: {e}")

def crawl_single_source(start_url, headers, max_pages, url_queue):  # Removed proxies
    """抓取单个来源的URL"""
    current_url = start_url
    page_count = 0
    while current_url and page_count < max_pages:
        logging.info(f"抓取: {current_url} (第 {page_count + 1}/{max_pages} 页，来源: {start_url})")
        html = fetch_page(current_url, headers)  # Removed proxies
        if html is None:
            break
        new_urls = get_urls_from_html(html)
        for url in new_urls:
            url_queue.put(url)
        current_url = get_next_page_url(html)
        page_count += 1
        time.sleep(random.uniform(35, 45))  # 随机延迟

def worker(url_queue, valid_urls, lock):
    """工作线程：验证URL"""
    while True:
        url = url_queue.get()
        if url is None:
            break
        if test_url_connectivity(url):
            with lock:
                valid_urls.add(url)
        url_queue.task_done()


def main(max_pages=10, num_threads=5):
    """主函数：多线程抓取"""

    # Get start_urls from the config file
    try:
        response = requests.get(CONFIG_URL_DECODED)
        response.raise_for_status()
        start_urls = [url.strip() for url in response.text.splitlines() if url.strip()]
        print(f"Loaded start URLs from config: {start_urls}")  # Debug print
    except requests.RequestException as e:
        logging.error(f"Failed to fetch start URLs from {CONFIG_URL_DECODED}: {e}")
        return  # Exit if cannot fetch start urls


    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()

    # 创建URL验证线程
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.start()
        threads.append(t)

    # 创建爬取线程
    for start_url in start_urls:
        # Removed proxies
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue)) # Removed proxies
        t.start()
        threads.append(t)

    # 等待爬取线程完成
    for t in threads[num_threads:]:
        t.join()

    # 停止验证线程
    for _ in range(num_threads):
        url_queue.put(None)
    for t in threads[:num_threads]:
        t.join()

    logging.info(f"所有来源抓取完毕")
    logging.info(f"有效 URL 数量: {len(valid_urls)}")

    #append and Save the result to Github repo.
    updated_content = append_urls_to_github(list(valid_urls), SUBSCRIBES_URL_DECODED)

    #save to local file temporarily
    if updated_content:
        filename = 'data/subscribes.txt'
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            logging.info(f"URL 已保存到 {filename}")
        except IOError as e:
            logging.error(f"保存 {filename} 失败: {e}")



if __name__ == '__main__':
    max_pages_to_crawl = 10
    main(max_pages_to_crawl)
