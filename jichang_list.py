import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_valid_url(url):
    """判断URL是否有效"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
    """从HTML中提取 URLs (改进了效率)"""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set()  # 使用集合存储 URLs，加速去重和判断

    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        urls.update(url for url in found_urls if is_valid_url(url))  # 添加非 Telegram  URL

    return list(urls)


def test_url_connectivity(url, timeout=5):
    """测试 URL 是否可连通 (增加超时)"""
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()  # 抛出 HTTPError，如果状态码 >= 400
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} 连接测试失败: {e}")
        return False


def get_next_page_url(html):
    """从HTML中提取下一页的URL"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more:
        next_page_url = 'https://t.me' + load_more['href']
        return next_page_url
    return None


def fetch_page(url, headers, timeout=10, max_retries=3):
    """抓取页面内容，带有重试机制"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()  # 确保状态码是 200
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"抓取页面 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 10))  # 重试前随机等待
            else:
                logging.error(f"抓取页面 {url} 失败，超出最大重试次数")
                return None
    return None  # 如果所有重试都失败

def save_urls_to_file(urls, filename='data/ji.txt'):
    """保存 URL 到文件"""
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        logging.info(f"URL 已保存到 {filename}")
    except IOError as e:
        logging.error(f"保存 URL 到文件 {filename} 失败: {e}")


def main(base_url='https://t.me/s/jichang_list', max_pages=90):
    """主函数，控制抓取流程"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    }

    all_urls = set()
    current_url = base_url
    page_count = 0

    while current_url and page_count < max_pages:
        logging.info(f"正在抓取页面: {current_url} (第 {page_count + 1}/{max_pages} 页)")

        html = fetch_page(current_url, headers)
        if html is None:
            break  # 抓取失败，停止

        new_urls = get_urls_from_html(html)
        all_urls.update(new_urls)

        next_page_url = get_next_page_url(html)
        current_url = next_page_url

        page_count += 1
        time.sleep(random.uniform(35, 45))  # 礼貌地随机延迟，避免被封

        # 保存中间结果
        save_urls_to_file(list(all_urls), 'data/ji_partial.txt') # 保存为中间文件，防止程序中断导致数据丢失

    # 验证 URL连通性
    valid_urls = [url for url in all_urls if test_url_connectivity(url)]

    logging.info(f"共抓取 {page_count} 页")
    logging.info(f"找到的 URL 总数: {len(all_urls)}")
    logging.info(f"有效的 URL 数量: {len(valid_urls)}")

    # 保存最终结果
    save_urls_to_file(valid_urls, 'data/jichang_list.txt')

if __name__ == '__main__':
    start_url = 'https://t.me/s/jichang_list'  # 你可以修改起始 URL
    max_pages_to_crawl = 30  # 你可以修改最大抓取页数
    main(start_url, max_pages_to_crawl)
