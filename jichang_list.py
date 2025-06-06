# jichang_list.py

import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# 配置日志
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User-Agent 池
# User-Agent pool
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
]

def is_valid_hostname(hostname):
    """
    检查主机名是否符合域名规则。
    Check if the hostname is valid according to domain name rules.
    """
    if not hostname or len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1] # 移除末尾的点
    allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(label) for label in hostname.split("."))

def is_valid_url(url):
    """
    通过检查其结构和主机名来验证URL。
    Validate the URL by checking its structure and hostname.
    """
    # 排除Telegram自身链接，避免无限循环或无关链接
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    if not is_valid_hostname(parsed.netloc):
        return False
    # 检查URL是否以无效前缀开头
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def clean_url(url):
    """
    从URL中移除末尾的标点符号。
    Remove trailing punctuation from the URL.
    """
    while url and url[-1] in '.,;:!?)':
        url = url[:-1]
    return url

def get_urls_from_html(html):
    """
    从HTML内容中提取并清理URL。
    Extract and clean URLs from HTML content.
    """
    soup = BeautifulSoup(html, 'html.parser')
    # 查找可能包含URL的元素类
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set() # 使用集合自动去重

    for target in targets:
        # 从 <a> 标签中提取
        for a_tag in target.find_all('a', href=True):
            href = clean_url(a_tag['href'].rstrip('/')) # 移除末尾斜杠和标点
            if is_valid_url(href):
                urls.add(href)
            else:
                logging.debug(f"从 <a> 标签中发现的无效URL已丢弃: {href}")

        # 从文本内容中提取
        text = target.get_text(separator=' ', strip=True)
        # 查找 http:// 或 https:// 或 www. 开头的URL
        found_urls_in_text = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text)
        for url_in_text in found_urls_in_text:
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text # 为 www. 开头的URL添加 http://
            url_in_text = clean_url(url_in_text.rstrip('/')) # 移除末尾斜杠和标点
            if is_valid_url(url_in_text):
                urls.add(url_in_text)
            else:
                logging.debug(f"从文本中发现的无效URL已丢弃: {url_in_text}")
    return list(urls) # 返回列表，方便后续处理

def test_url_connectivity(url, timeout=10):
    """
    测试URL是否可连接。
    Test if the URL is connectable.
    """
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        # 使用 HEAD 请求，只获取头部信息，更快
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return response.status_code == 200 # 200 OK 表示连接成功
    except requests.RequestException:
        return False

def get_next_page_url(html):
    """
    从HTML中提取下一页的URL。
    Extract the next page URL from HTML.
    """
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more') # 查找“加载更多”按钮
    if load_more and load_more.has_attr('href'):
        # 补全为完整的URL
        return 'https://t.me' + load_more['href']
    return None

def load_existing_urls(filename='./trial.cfg'):
    """
    从文件中加载已有的URL集合。
    Load existing URLs from a file into a set.
    """
    existing_urls = set()
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url:
                        existing_urls.add(url)
            logging.info(f"已从 {filename} 加载 {len(existing_urls)} 个现有URL。")
        except IOError as e:
            logging.error(f"加载现有URL失败 {filename}: {e}")
    else:
        logging.info(f"文件 {filename} 不存在，将创建新文件。")
    return existing_urls

def save_urls_to_file(new_urls, filename='./trial.cfg'):
    """
    将URL保存到文件，并确保文件内容去重。
    Save URLs to a file, ensuring the file content is de-duplicated.
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # 1. 加载现有URL
    existing_urls = load_existing_urls(filename) # 实际上这个函数内部已经有日志了

    # 2. 合并新旧URL并去重
    all_urls = existing_urls.union(new_urls) # 使用集合的union操作，自动去重

    try:
        # 3. 将所有去重后的URL重新写入文件 (覆盖模式 'w')
        with open(filename, 'w', encoding='utf-8') as f:
            for url in sorted(list(all_urls)): # 排序后写入，方便查看
                f.write(url + '\n')
        logging.info(f"所有去重后的URL已保存到 {filename} (总数: {len(all_urls)})")
    except IOError as e:
        logging.error(f"保存URL到 {filename} 失败: {e}")

def main(start_urls, max_pages_per_source=90, max_workers=10):
    """
    控制抓取过程的主函数。
    Main function to control the scraping process.
    """
    # 初始化总的URL集合，并加载文件中已存在的URL，实现跨次运行的去重
    # Initialize the overall URL set and load existing URLs from file for cross-run de-duplication
    overall_found_urls = load_existing_urls('./trial.cfg')
    
    processed_page_count_total = 0

    for base_url in start_urls:
        logging.info(f"======== 开始处理来源: {base_url} ========")
        # current_source_urls = set() # 这个集合用于跟踪当前来源找到的URL，但最终都合并到overall_found_urls
        current_url = base_url
        page_count_for_source = 0

        while current_url and page_count_for_source < max_pages_per_source:
            logging.info(f"正在抓取页面: {current_url} (来源: {base_url}, 第 {page_count_for_source + 1}/{max_pages_per_source} 页)")
            html = fetch_page(current_url)
            if html is None:
                logging.warning(f"无法从 {current_url} 获取内容，停止此来源的抓取。")
                break

            new_urls = get_urls_from_html(html)
            if new_urls:
                logging.info(f"此页面发现 {len(new_urls)} 个新URL。")
                # current_source_urls.update(new_urls) # 可以取消此行，因为最终都到overall_found_urls
                overall_found_urls.update(new_urls) # 直接添加到总集合中
                # logging.info(f"当前来源URL数量: {len(current_source_urls)}") # 可以取消此行
                logging.info(f"所有来源发现的总URL数量: {len(overall_found_urls)}")

            next_page_url = get_next_page_url(html)
            current_url = next_page_url
            page_count_for_source += 1
            processed_page_count_total += 1
            time.sleep(random.uniform(20, 40)) # 随机延迟，避免被封禁

        logging.info(f"======== 来源 {base_url} 处理完毕，共处理 {page_count_for_source} 页 ========")

    logging.info(f"\n======== 所有来源处理完毕，总页数: {processed_page_count_total} ========")
    logging.info(f"所有来源发现的唯一URL总数: {len(overall_found_urls)}")

    if not overall_found_urls:
        logging.info("没有找到可进行连通性测试的URL。")
    else:
        logging.info("开始并发URL连通性测试...")
        valid_urls_set = set() # 使用集合存储有效的URL
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # overall_found_urls 是一个集合，需要转换为列表才能传递给 map
            # 使用 zip 将原始URL与测试结果配对
            for url, is_connectable in zip(list(overall_found_urls), executor.map(test_url_connectivity, list(overall_found_urls))):
                if is_connectable:
                    valid_urls_set.add(url) # 添加到有效的URL集合中

        logging.info(f"连通性测试完成。有效URL数量: {len(valid_urls_set)}")
        logging.info("正在保存最终有效URL...")
        save_urls_to_file(valid_urls_set, './trial.cfg') # 传入集合
        logging.info("最终结果已保存。")

if __name__ == '__main__':
    start_urls_list = [
        'https://t.me/s/jichang_list',
        # 'https://t.me/s/another_channel_example', # 您可以添加更多起始URL
    ]
    max_pages_to_crawl_per_source = 18 # 每个来源最多抓取的页数
    concurrent_workers = 15 # 并发测试URL连通性的工作线程数

    main(start_urls_list, max_pages_to_crawl_per_source, concurrent_workers)
