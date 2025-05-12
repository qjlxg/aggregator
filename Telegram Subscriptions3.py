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
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36',
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    'Mozilla/5.0 (compatible; DuckDuckBot/1.0; libcurl/7.64.1)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave/92.1.27.111 Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Brave/92.1.27.111 Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.105 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 9; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 7.0; SM-G935F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.83 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 11; Redmi Note 10 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1',
]

def get_random_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}

def is_valid_url(url):
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def extract_subscribe_urls(html):
    """从 HTML 中提取包含 'subscribe?token=' 的 URL。"""
    soup = BeautifulSoup(html, 'html.parser')
    target_classes = [
        'tgme_widget_message_text', 'tgme_widget_message_photo',
        'tgme_widget_message_video', 'tgme_widget_message_document',
        'tgme_widget_message_poll'
    ]
    excluded_domains = ("aliyundrive.com", "pan.baidu.com")
    urls = set()
    for target in soup.find_all(class_=target_classes):
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        valid_urls = [url for url in found_urls if "subscribe?token=" in url or "/s/" in url or url.startswith("http://") or url.startswith("https://")
        and not any(domain in url for domain in excluded_domains)]
        urls.update(valid_urls)
    return list(urls)

def check_url_connectivity(url, timeout=5):
    """测试 URL 的连通性。"""
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} 连接测试失败: {e}")
        return False

def get_next_page(html):
    """从 HTML 中提取下一页的 URL。"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more:
        next_page_url = 'https://t.me' + load_more['href']
        logging.info(f"找到下一页 URL: {next_page_url}")
        return next_page_url
    else:
        logging.info("没有找到下一页 URL")
        return None

def fetch_html(url, headers, timeout=10, max_retries=3):
    """抓取指定 URL 的 HTML 内容，带有重试机制。"""
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

def save_to_local_file(file_path, content):
    """将内容保存到本地文件。"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content) + '\n')
        logging.info(f"内容保存到本地文件: {file_path}")
        return True
    except Exception as e:
        logging.error(f"保存到本地文件失败: {e}")
        return False

def crawl_source(start_url, headers, max_pages, url_queue):
    """抓取单个来源的 URL。"""
    current_url = start_url
    for page_num in range(max_pages):
        logging.info(f"抓取: {current_url} (第 {page_num + 1}/{max_pages} 页，来源: {start_url})")
        html = fetch_html(current_url, headers)
        if not html:
            logging.warning(f"无法获取 {current_url} 的 HTML，停止从此来源抓取")
            break
        new_urls = extract_subscribe_urls(html)
        logging.info(f"从 {current_url} 提取到 {len(new_urls)} 个 URL")
        for url in new_urls:
            url_queue.put(url)
        current_url = get_next_page(html)
        if not current_url:
            logging.info(f"{start_url} 没有下一页，抓取结束")
            break
        sleep_time = random.uniform(35, 45)
        logging.info(f"等待 {sleep_time:.2f} 秒后抓取下一页")
        time.sleep(sleep_time)

def worker(url_queue, valid_urls, lock):
    """工作线程，用于检查 URL 的连通性。"""
    while True:
        url = url_queue.get()
        if url is None:
            logging.info("worker 收到停止信号，退出")
            break
        try:
            if check_url_connectivity(url):
                with lock:
                    valid_urls.add(url)
                logging.info(f"URL {url} 有效，已添加到有效 URL 集合")
            else:
                logging.warning(f"URL {url} 连接测试失败")
        except Exception as e:
            logging.error(f"测试 URL {url} 的连接性时发生错误: {e}")
        finally:
            url_queue.task_done()

def main(start_urls, max_pages=10, num_threads=5, output_file='data/xujw3.txt'):
    """主函数，协调抓取和保存过程。"""
    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()
    threads = []

    # 启动工作线程
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.daemon = True
        t.start()
        threads.append(t)

    crawler_threads = []
    # 启动爬虫线程
    for start_url in start_urls:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_source, args=(start_url, headers, max_pages, url_queue))
        t.daemon = True
        t.start()
        crawler_threads.append(t)

    # 等待所有爬虫线程完成
    for t in crawler_threads:
        t.join()

    # 向工作线程发送停止信号
    for _ in range(num_threads):
        url_queue.put(None)

    # 等待所有工作线程完成
    for t in threads:
        t.join()

    logging.info(f"所有线程已退出")
    logging.info(f"有效 URL 数量: {len(valid_urls)}")

    # 保存结果到本地文件
    save_to_local_file(output_file, list(valid_urls))

if __name__ == '__main__':
    config_file_path = 'config.txt'
    start_urls_list = []

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            start_urls_list = [line.strip() for line in f if line.strip()]
        logging.info(f"从本地文件 {config_file_path} 读取到 {len(start_urls_list)} 个起始 URL")
    except FileNotFoundError:
        logging.error(f"找不到配置文件: {config_file_path}。请确保该文件位于根目录下。")
    except Exception as e:
        logging.error(f"读取配置文件 {config_file_path} 失败: {e}")

    max_pages_to_crawl = 3
    num_working_threads = 5
    output_filename = 'data/xujw3.txt'
    main(start_urls_list, max_pages_to_crawl, num_working_threads, output_filename)
