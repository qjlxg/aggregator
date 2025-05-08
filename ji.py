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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 请求头池 ... (保持不变)

def get_random_headers():
    # ... (保持不变)

def is_valid_url(url):
    # ... (保持不变)

def get_urls_from_html(html):
    # ... (保持不变)

def test_url_connectivity(url, timeout=5):
    # ... (保持不变)

def get_next_page_url(html):
    # ... (保持不变)

def fetch_page(url, headers, timeout=10, max_retries=3):
    # ... (保持不变)

def save_urls_to_github(repo_name, file_path, content, github_token):
    """保存内容到 GitHub 私有仓库"""
    g = Github(github_token)
    repo = g.get_user().get_repo(repo_name)
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
    # ... (保持不变)

def worker(url_queue, valid_urls, lock):
    # ... (保持不变)

def main(start_urls, max_pages=10, num_threads=5, github_token=None):
    """主函数：多线程抓取"""
    logging.info(f"GitHub Token 存在: {bool(github_token)}") # 检查 Token 是否传递进来

    # 临时调试代码 - 检查 Token 是否有效
    try:
        g = Github(github_token)
        user = g.get_user()
        logging.info(f"GitHub 用户名: {user.login}")
    except Exception as e:
        logging.error(f"GitHub API 认证失败: {e}")

    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()

    # 创建URL验证线程 ... (保持不变)
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.start()
        threads.append(t)

    # 创建爬取线程 ... (保持不变)
    for start_url in start_urls:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue))
        t.start()
        threads.append(t)

    # 等待爬取线程完成 ... (保持不变)
    for t in threads[num_threads:]:
        t.join()

    # 停止验证线程 ... (保持不变)
    for _ in range(num_threads):
        url_queue.put(None)
    for t in threads[:num_threads]:
        t.join()

    logging.info(f"所有来源抓取完毕")
    logging.info(f"有效 URL 数量: {len(valid_urls)}")

    if github_token:
        repo_name = 'qjlxg/362' # 隐藏仓库地址
        file_path = 'data/subscribes.txt' # 隐藏仓库路径
        save_urls_to_github(repo_name, file_path, list(valid_urls), github_token)


if __name__ == '__main__':
    github_token = os.environ.get('GT_TOKEN') # 使用 GT_TOKEN

    # 从私有仓库读取 config.txt 中的 URL
    config_repo_name = 'qjlxg/362' # 隐藏仓库地址
    config_file_path = 'data/config.txt' # 隐藏仓库路径
    start_urls_list = []

    try:
        g = Github(github_token)
        repo = g.get_user().get_repo(config_repo_name)
        config_content_file = repo.get_contents(config_file_path)
        config_content = config_content_file.decoded_content.decode('utf-8')
        start_urls_list = [url.strip() for url in config_content.strip().split('\n') if url.strip()]
        logging.info(f"从 GitHub 读取到 {len(start_urls_list)} 个起始 URL")
    except Exception as e:
        logging.error(f"无法从 GitHub 读取配置文件: {e}")
        # 如果无法读取，可以使用一个空的列表作为备用
        start_urls_list = []

    max_pages_to_crawl = 10
    main(start_urls_list, max_pages_to_crawl, github_token=github_token)
