import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue

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
        # Only keep URLs containing "subscribe?token="
        valid_urls = [url for url in found_urls if "subscribe?token=" in url]
        urls.update(valid_urls)
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
    if load_more:
        next_page_url = 'https://t.me' + load_more['href']
        logging.info(f"找到下一页 URL: {next_page_url}")
        return next_page_url
    else:
        logging.info("没有找到下一页 URL")
        return None

def fetch_page(url, headers, timeout=10, max_retries=3):
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            end_time = time.time()
            logging.info(f"成功抓取 {url} (尝试 {attempt + 1}/{max_retries}), 耗时: {end_time - start_time:.2f}秒")
            return response.text
        except requests.RequestException as e:
            logging.warning(f"抓取 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                sleep_time = random.uniform(38, 53)
                logging.info(f"等待 {sleep_time:.2f} 秒后重试")
                time.sleep(sleep_time)
            else:
                logging.error(f"抓取 {url} 失败，超出最大重试次数: {e}")
                return None

def save_urls_to_local(file_path, content):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content) + '\n')
        logging.info(f"URL 保存到本地文件: {file_path}")
        return True
    except Exception as e:
        logging.error(f"保存到本地文件失败: {e}")
        return False


def crawl_single_source(start_url, headers, max_pages, url_queue):
    current_url = start_url
    page_count = 0
    while current_url and page_count < max_pages:
        logging.info(f"抓取: {current_url} (第 {page_count + 1}/{max_pages} 页，来源: {start_url})")
        html = fetch_page(current_url, headers)
        if html is None:
            logging.warning(f"无法获取 {current_url} 的 HTML，停止从此来源抓取")
            break
        new_urls = get_urls_from_html(html)
        logging.info(f"从 {current_url} 提取到 {len(new_urls)} 个 URL")
        for url in new_urls:
            url_queue.put(url)
        current_url = get_next_page_url(html)
        page_count += 1
        sleep_time = random.uniform(35, 45)
        logging.info(f"等待 {sleep_time:.2f} 秒后抓取下一页")
        time.sleep(sleep_time)

def worker(url_queue, valid_urls, lock):
    while True:
        url = url_queue.get()
        if url is None:
            logging.info("worker 收到停止信号，退出")
            break
        try:
            if test_url_connectivity(url):
                with lock:
                    valid_urls.add(url)
                logging.info(f"URL {url} 有效，已添加到有效 URL 集合")
            else:
                logging.warning(f"URL {url} 连接测试失败")

        except Exception as e:
            logging.error(f"测试 URL {url} 的连接性时发生错误: {e}")
        finally:
            url_queue.task_done()

def main(start_urls, max_pages=10, num_threads=5):

    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()

    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.daemon = True  # 设置为守护线程
        t.start()
        threads.append(t)

    crawler_threads = [] #单独保存爬虫线程，方便join
    for start_url in start_urls:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue))
        t.daemon = True  # 设置为守护线程
        t.start()
        crawler_threads.append(t)

    for t in crawler_threads: #等待爬虫线程结束
        t.join()

    # Queue的所有task都完成后，再发送结束信号
    url_queue.join()

    logging.info("所有来源抓取任务已完成. 发送停止信号给 worker")

    for _ in range(num_threads):
        url_queue.put(None) # 发送停止信号
    for t in threads:
        t.join()

    logging.info(f"所有worker线程已退出")
    logging.info(f"有效 URL 数量: {len(valid_urls)}")

    # 保存到本地文件
    local_file_path = 'data/subscribes.txt'
    save_urls_to_local(local_file_path, list(valid_urls))


if __name__ == '__main__':
    config_file_path = 'config.txt'  # 设置为根目录下的 config.txt
    start_urls_list = []

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url:
                    start_urls_list.append(url)
        logging.info(f"从本地文件 {config_file_path} 读取到 {len(start_urls_list)} 个起始 URL")
    except FileNotFoundError:
        logging.error(f"找不到配置文件: {config_file_path}。请确保该文件位于根目录下。")
    except Exception as e:
        logging.error(f"读取配置文件 {config_file_path} 失败: {e}")

    max_pages_to_crawl = 10
    num_working_threads = 5
    main(start_urls_list, max_pages_to_crawl, num_working_threads)
