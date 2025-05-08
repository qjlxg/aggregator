import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

# 环境变量 Keys
CONFIG_URL_ENV = "CONFIG_URL"
SUBSCRIBE_URL_ENV = "SUBSCRIBE_URL"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

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

def get_start_urls_from_config(config_url):
    """从配置URL获取起始URL列表"""
    try:
        response = requests.get(config_url)
        response.raise_for_status()
        return response.text.strip().splitlines()
    except requests.RequestException as e:
        logging.error(f"获取配置失败: {e}")
        return []

def save_urls_to_github(urls, repo_url, github_token):
    
    try:
        # GitHub API 需要去掉 raw
        api_url = repo_url.replace('/raw/refs/heads/main', '/contents/data/subscribes.txt')
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # 获取现有文件内容和 sha 值
        get_response = requests.get(api_url, headers=headers)
        get_response.raise_for_status()
        existing_data = get_response.json()
        sha = existing_data['sha']
        content = existing_data.get('content', '')
        if content:
            import base64
            content = base64.b64decode(content).decode('utf-8')

        updated_content = content + "\n".join(urls) + "\n"

        # Base64 编码新内容
        import base64
        updated_content_encoded = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')

        # 构建更新请求
        data = {
            "message": "Add new URLs",
            "content": updated_content_encoded,
            "sha": sha,
            "branch": "main"
        }

        put_response = requests.put(api_url, headers=headers, json=data)
        put_response.raise_for_status()
        logging.info("URL 已追加保存到 GitHub 仓库 .")

    except requests.RequestException as e:
        logging.error(f"保存到 GitHub 仓库失败: {e}")
    except KeyError as e:
        logging.error(f"解析 GitHub API 响应失败: {e}")


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


def main(config_url, subscribe_url, github_token, max_pages=10, num_threads=5):
    """主函数：多线程抓取"""
    start_urls = get_start_urls_from_config(config_url)
    if not start_urls:
        logging.error("未获取到起始 URL，程序终止。")
        return

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
    save_urls_to_github(list(valid_urls), subscribe_url, github_token)



if __name__ == '__main__':
    config_url = os.getenv(CONFIG_URL_ENV)
    subscribe_url = os.getenv(SUBSCRIBE_URL_ENV)
    github_token = os.getenv(GITHUB_TOKEN_ENV)

    if not config_url or not subscribe_url or not github_token:
        logging.error("请设置 CONFIG_URL, SUBSCRIBE_URL 和 GITHUB_TOKEN 环境变量。")
    else:
        max_pages_to_crawl = 10
        main(config_url, subscribe_url, github_token, max_pages_to_crawl)
