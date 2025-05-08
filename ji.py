import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue
import base64
import configparser

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 请求头池
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

def get_config_from_github(repo_url, token):
    
    config_url = f"{repo_url}/raw/refs/heads/main/data/config.ini"
    headers = {'Authorization': f'token {token}'}
    response = requests.get(config_url, headers=headers)
    response.raise_for_status()
    config_content = response.text
    config = configparser.ConfigParser()
    config.read_string(config_content)
    
    urls = [config['urls'][key] for key in config['urls']]
    return urls

def update_subscribes_txt(repo_url, token, new_urls):
    
    api_url = f"https://api.github.com/repos/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/contents/data/subscribes.txt"
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    
    # 获取当前文件内容
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        file_data = response.json()
        current_content = base64.b64decode(file_data['content']).decode('utf-8')
        sha = file_data['sha']
    else:
        current_content = ""
        sha = None
    
    # 追加新 URL
    updated_content = current_content + '\n'.join(new_urls) + '\n'
    encoded_content = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')
    
    # 更新文件
    data = {
        'message': 'Append new URLs',
        'content': encoded_content,
        'sha': sha if sha else ''
    }
    response = requests.put(api_url, headers=headers, json=data)
    response.raise_for_status()
    logging.info("成功更新 subscribes.txt")

def crawl_single_source(start_url, headers, max_pages, url_queue):
    """抓取单个来源的URL"""
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
    
    token = os.getenv('GITHUB_TOKEN')
    repo_url = os.getenv('REPO_URL', 'https://github.com/qjlxg/362')
    
    if not token:
        logging.error("未设置 GITHUB_TOKEN 环境变量")
        return
    
    # 从 config.ini 获取 URL 列表
    try:
        start_urls_list = get_config_from_github(repo_url, token)
    except Exception as e:
        logging.error(f"获取 config.ini 失败: {e}")
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
    for start_url in start_urls_list:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue))
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
    
    
    try:
        update_subscribes_txt(repo_url, token, list(valid_urls))
    except Exception as e:
        logging.error(f"更新 subscribes.txt 失败: {e}")

if __name__ == '__main__':
    main()
