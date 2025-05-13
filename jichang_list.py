import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 增强User-Agent池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.1 Safari/605.1.15',
    'Mozilla/5.0 (Linux; Android 10; SM-G9750) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.72 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    # 可以继续添加
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def is_valid_url(url):
    """判断URL是否有效，排除Telegram相关"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
    """从HTML中提取 URLs"""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set()
    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        urls.update(url for url in found_urls if is_valid_url(url))
    return list(urls)

def test_url_connectivity(url, timeout=5):
    """测试 URL 是否可连通，返回（url, bool）"""
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        return url, True
    except requests.RequestException:
        return url, False

def get_next_page_url(html):
    """从HTML中提取下一页链接，仅支持Telegram页面"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more:
        next_page_url = 'https://t.me' + load_more['href']
        return next_page_url
    return None

def fetch_page(url, headers, timeout=10, max_retries=3):
    """带重试的页面抓取"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.warning(f"抓取 {url} 失败尝试 {attempt+1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 10))
            else:
                logging.error(f"多次尝试后抓取失败: {url}")
                return None
    return None

def save_urls_to_file(urls, filename):
    """保存URL列表到文件"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        logging.info(f"已保存 {len(urls)} 条URL到 {filename}")
    except IOError as e:
        logging.error(f"保存到文件失败: {filename}, 错误: {e}")

def crawl_single_start(start_url, max_pages):
    """对单个入口URL进行爬取"""
    headers = {
        'User-Agent': get_random_user_agent()
    }
    all_urls = set()
    current_url = start_url
    page_count = 0

    while current_url and page_count < max_pages:
        headers['User-Agent'] = get_random_user_agent()
        logging.info(f"[{start_url}] 第 {page_count+1} 页：抓取 {current_url}")
        html = fetch_page(current_url, headers)
        if html is None:
            logging.warning("页面抓取失败，停止此入口的抓取。")
            break
        new_urls = get_urls_from_html(html)
        logging.info(f"[{start_url}] 当前页面提取到 {len(new_urls)} 个链接")
        all_urls.update(new_urls)

        next_page_url = get_next_page_url(html)
        current_url = next_page_url
        page_count += 1

        # 随机延迟，礼貌爬取
        time.sleep(random.uniform(39, 58))
        # 中间文件保存（可选）
        save_urls_to_file(list(all_urls), 'data/partial_' + re.sub(r'[^\w]', '_', start_url) + '.txt')

    return all_urls

def main(start_urls, max_pages=90, max_workers=5):
    """支持多个入口的主函数"""
    all_urls = set()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(crawl_single_start, url, max_pages) for url in start_urls]
        for future in as_completed(futures):
            try:
                result = future.result()
                all_urls.update(result)
            except Exception as e:
                logging.error(f"某入口抓取出错: {e}")

    # 保存所有URL
    save_urls_to_file(sorted(all_urls), 'data/jichang.txt')
    logging.info(f"总共抓取到 {len(all_urls)} 条有效链接。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='多入口Telegram网页爬取脚本', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--start_urls", nargs="+", required=True, help="多个入口URL，用空格分隔")
    parser.add_argument("--max_pages", type=int, default=5, help="最大页数")
    parser.add_argument("--max_workers", type=int, default=5, help="最大并发线程数")
    args = parser.parse_args()

    start_urls = args.start_urls
    max_pages = args.max_pages
    max_workers = args.max_workers

    main(start_urls, max_pages, max_workers)
