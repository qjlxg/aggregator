import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue

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


def main(start_urls, max_pages=10, num_threads=5):
    """主函数：多线程抓取"""
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
    save_urls_to_file(list(valid_urls), 'data/ji.txt')


if __name__ == '__main__':
    start_urls_list = [
'https://t.me/s/vpn_3000',
'https://t.me/s/academi_vpn',
'https://t.me/s/dingyue_center',
'https://t.me/s/freedatazone1',
'https://t.me/s/freev2rayi',
'https://t.me/s/mypremium98',
'https://t.me/s/tigervpn_free',
'https://t.me/s/inikotesla',
'https://t.me/s/iSegaro',
'https://t.me/s/v2rayngalpha',
'https://t.me/s/v2rayngalphagamer',
'https://t.me/s/jiedian_share',
'https://t.me/s/vpn_mafia',
'https://t.me/s/dr_v2ray',
'https://t.me/s/litevp',
'https://t.me/s/allv2board',
'https://t.me/s/bigsmoke_config',
'https://t.me/s/vpn_443',
'https://t.me/s/prossh',
'https://t.me/s/mftizi',
'https://t.me/s/qun521',
'https://t.me/s/haoshangle',
'https://t.me/s/v2rayng_my2',
'https://t.me/s/go4sharing',
'https://t.me/s/wearestand',
'https://t.me/s/trand_farsi',
'https://t.me/s/vpnplusee_free',
'https://t.me/s/freekankan',
'https://t.me/s/awxdy666',

      
    ]
    max_pages_to_crawl = 10
    main(start_urls_list, max_pages_to_crawl)
