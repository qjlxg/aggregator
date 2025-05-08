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


def get_file_from_github(token, file_path, branch='main'):
    """从 GitHub 获取文件内容"""
    api_url = f"https://api.github.com/repos/qjlxg/362/contents/{file_path}?ref={branch}"
    masked_url = re.sub(r'https://api\.github\.com/repos/.*?/contents/.*?\?ref=.*', r'https://api.github.com/repos/<repo>/contents/<file>?ref=<branch>', api_url)
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3.raw'
    }
    logging.info(f"尝试访问: {masked_url}")
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查 HTTP 状态码
        return response.text
    except requests.RequestException as e:
        logging.error(f"获取 {file_path} 失败: {e}")
        return None


def append_to_github_file(token, file_path, content, branch='main'):
    """将内容追加到 GitHub 仓库的文件中"""
    # 获取仓库信息和文件 SHA
    api_url = f"https://api.github.com/repos/qjlxg/362/contents/{file_path}?ref={branch}"
    masked_url = re.sub(r'https://api\.github\.com/repos/.*?/contents/.*?\?ref=.*', r'https://api.github.com/repos/<repo>/contents/<file>?ref=<branch>', api_url)
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        file_data = response.json()
        sha = file_data['sha']

        # 获取现有文件内容
        existing_content_encoded = file_data.get('content', '')
        if existing_content_encoded:
            existing_content = base64.b64decode(existing_content_encoded).decode('utf-8')
        else:
            existing_content = ''

        # 追加新内容
        updated_content = existing_content + content

        # 编码新内容
        updated_content_encoded = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')

        # 构建 PUT 请求
        put_data = {
            "message": f"Append to {file_path}",
            "content": updated_content_encoded,
            "sha": sha,
            "branch": branch
        }
        put_response = requests.put(api_url, headers=headers, json=put_data)
        put_response.raise_for_status()
        logging.info(f"成功追加到 {file_path}")
    except requests.RequestException as e:
        logging.error(f"追加到 {file_path} 失败: {e}")


def main(max_pages=10, num_threads=5):
    """主函数：多线程抓取"""
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        logging.error("未设置 GITHUB_TOKEN 环境变量")
        return

    # 从 config.txt 读取 start_urls_list
    config_content = get_file_from_github(token, 'data/config.txt')
    if not config_content:
        logging.error("无法从 GitHub 读取 config.txt")
        return

    # 将文件内容按行分割为 URL 列表
    start_urls_list = [url.strip() for url in config_content.splitlines() if url.strip()]

    logging.info(f"从 config.txt 读取到的 start_urls: {start_urls_list}")

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

    # 将结果追加保存到 subscribes.txt
    results_string = '\n'.join(valid_urls) + '\n'
    append_to_github_file(token, 'data/subscribes.txt', results_string)


if __name__ == '__main__':
    max_pages_to_crawl = 10
    main(max_pages_to_crawl)
