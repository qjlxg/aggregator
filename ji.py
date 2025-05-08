import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue
from github import Github

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0'
]

def get_random_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}

def is_valid_url(url):
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
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
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} 连接测试失败: {e}")
        return False

def get_next_page_url(html):
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    return 'https://t.me' + load_more['href'] if load_more else None

def fetch_page(url, headers, timeout=10, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.warning(f"抓取 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(38, 53))
            else:
                logging.error(f"抓取 {url} 失败，超出最大重试次数")
                return None

def save_urls_to_github(repo_name, file_path, content, github_token):
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    try:
        contents = repo.get_contents(file_path)
        updated_content = contents.decoded_content.decode('utf-8') + '\n' + '\n'.join(content)
        repo.update_file(contents.path, "Add new subscriptions", updated_content.encode('utf-8'), contents.sha)
        logging.info(f"URL 追加保存到 GitHub: {repo_name}/{file_path}")
    except Exception as e:
        repo.create_file(file_path, "Initial subscriptions", '\n'.join(content).encode('utf-8'))
        logging.info(f"URL 首次保存到 GitHub: {repo_name}/{file_path}")
    return True

def crawl_single_source(start_url, headers, max_pages, url_queue):
    current_url = start_url
    page_count = 0
    while current_url and page_count < max_pages:
        logging.info(f"抓取: {current_url} (第 {page_count + 1}/{max_pages} 页，来源: {start_url})")
        html = fetch_page(current_url, headers)
        if html is None:
            break
        new_urls = get_urls_from_html(html)
        for url in new_urls:
            url_queue.put(url)
        current_url = get_next_page_url(html)
        page_count += 1
        time.sleep(random.uniform(35, 45))

def worker(url_queue, valid_urls, lock):
    while True:
        url = url_queue.get()
        if url is None:
            break
        if test_url_connectivity(url):
            with lock:
                valid_urls.add(url)
        url_queue.task_done()

def main(start_urls, max_pages=10, num_threads=5, github_token=None):
    logging.info(f"GitHub Token 存在: {bool(github_token)}")

    try:
        g = Github(github_token)
        user = g.get_user()
        logging.info(f"GitHub 用户名: {user.login}")
    except Exception as e:
        logging.error(f"GitHub API 认证失败: {e}")

    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()

    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.start()
        threads.append(t)

    for start_url in start_urls:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue))
        t.start()
        threads.append(t)

    for t in threads[num_threads:]:
        t.join()

    for _ in range(num_threads):
        url_queue.put(None)
    for t in threads[:num_threads]:
        t.join()

    logging.info(f"所有来源抓取完毕")
    logging.info(f"有效 URL 数量: {len(valid_urls)}")

    if github_token:
        repo_name = 'qjlxg/362'
        file_path = 'data/subscribes.txt'
        save_urls_to_github(repo_name, file_path, list(valid_urls), github_token)

if __name__ == '__main__':
    github_token = os.environ.get('GT_TOKEN')

    config_repo_name = 'qjlxg/362'
    config_file_path = 'data/config.txt'
    start_urls_list = []

    try:
        g = Github(github_token)
        repo = g.get_repo(config_repo_name)
        config_content_file = repo.get_contents(config_file_path)
        config_content = config_content_file.decoded_content.decode('utf-8')
        start_urls_list = [url.strip() for url in config_content.strip().split('\n') if url.strip()]
        logging.info(f"从 GitHub 读取到 {len(start_urls_list)} 个起始 URL")
    except Exception as e:
        logging.error(f"无法从 GitHub 读取配置文件: {e}")
        start_urls_list = []

    max_pages_to_crawl = 10
    main(start_urls_list, max_pages_to_crawl, github_token=github_token)
