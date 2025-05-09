import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from urllib.parse import urljoin, quote

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_valid_url(url):
    """判断URL是否有效"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html, base_url):
    """从HTML中提取 URLs (改进了效率，并处理相对路径)"""
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
        for found_url in found_urls:
            if is_valid_url(found_url):
                urls.add(found_url)
            # 处理 Telegram 内部链接, 提取完整的URL。
            elif found_url.startswith('/'):
                absolute_url = urljoin(base_url, found_url)
                urls.add(absolute_url)

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

def save_urls_to_file(urls, filename='data/ji_partial.txt'):
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



def search_url_in_telegram(start_url, keyword, max_pages=90):
    """
    在 Telegram 频道中搜索包含特定关键词的 URL.

    参数:
        start_url (str): 起始 URL.
        keyword (str): 要搜索的关键词.
        max_pages (int): 最大抓取页数.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    }
    all_urls = set()
    current_url = start_url
    page_count = 0
    found_count = 0 # 记录找到的URL数量

    while current_url and page_count < max_pages:
        logging.info(f"正在抓取页面: {current_url} (第 {page_count + 1}/{max_pages} 页)")
        html = fetch_page(current_url, headers)
        if html is None:
            break
        urls = get_urls_from_html(html, current_url) # 传递 current_url
        for url in urls:
            if keyword in url:
                all_urls.add(url)
                found_count += 1
                logging.info(f"找到匹配的 URL: {url}")

        next_page_url = get_next_page_url(html)
        current_url = next_page_url
        page_count += 1
        time.sleep(random.uniform(35, 45))

        save_urls_to_file(list(all_urls), 'data/ji_partial.txt')
        logging.info(f"已保存 {len(all_urls)} 个 URLs 到 data/ji_partial.txt")

    logging.info(f"共抓取 {page_count} 页")
    logging.info(f"找到包含关键词 '{keyword}' 的 URL 总数: {len(all_urls)}")
    save_urls_to_file(list(all_urls), 'data/ji_partial.txt.txt')
    return list(all_urls)



def main():
    """主函数"""
    start_url = 'https://t.me/s/dingyue_center' # 种子URL，用于发现频道消息。 # 修改了起始URL
    keyword = "/api/v1/client/subscribe?token="
    search_results = search_url_in_telegram(start_url, keyword)
    if search_results:
        logging.info(f"找到以下包含关键词 '{keyword}' 的 URL:")
        for url in search_results:
            logging.info(url)
    else:
        logging.info(f"未找到包含关键词 '{keyword}' 的 URL.")



if __name__ == "__main__":
    main()
