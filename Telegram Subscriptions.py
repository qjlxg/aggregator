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
    excluded_domains = ("aliyundrive.com", "pan.baidu.com")
    urls = set()
    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        # Only keep URLs containing "subscribe?token="
        valid_urls = [url for url in found_urls if "subscribe?token=" in url or "/s/" in url or url.startswith("http://") or url.startswith("https://")
        and not any(domain in url for domain in excluded_domains)]
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

def save_urls_to_github(repo_name, file_path, content, github_token):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents(file_path)
            updated_content = contents.decoded_content.decode('utf-8') + '\n' + '\n'.join(content)
            repo.update_file(contents.path, "Add new subscriptions", updated_content.encode('utf-8'), contents.sha)
            logging.info(f"URL 追加保存到 GitHub: {repo_name}/{file_path}")
            return True
        except Exception as e:
            if "Not Found" in str(e):
                repo.create_file(file_path, "Initial subscriptions", '\n'.join(content).encode('utf-8'))
                logging.info(f"URL 首次保存到 GitHub: {repo_name}/{file_path}")
                return True
            else:
                logging.error(f"保存到 GitHub 失败: {e}")
                return False
    except Exception as e:
        logging.error(f"GitHub API 认证或仓库访问失败: {e}")
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

def main(start_urls, max_pages=10, num_threads=5, github_token=None):

    if github_token:
      logging.info(f"GitHub Token 存在!")
    else:
      logging.warning(f"GitHub Token 不存在，将不会保存到GitHub")

    if github_token:
        try:
            g = Github(github_token)
            user = g.get_user()
            logging.info(f"GitHub 用户名: {user.login}")
        except Exception as e:
            logging.error(f"GitHub API 认证失败: {e}")
            github_token = None # 设置为None，避免后续保存操作

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

    if github_token: #再次检查github_token
        repo_name = 'qjlxg/362'
        file_path = 'data/subscribes.txt'
        if(save_urls_to_github(repo_name, file_path, list(valid_urls), github_token)): #如果保存成功
            logging.info("成功将URL保存到github")
        else:
            logging.error("将URL保存到github失败")



if __name__ == '__main__':
    github_token = os.environ.get('GT_TOKEN')

    config_repo_name = 'qjlxg/362'
    config_file_path = 'data/config.txt'
    start_urls_list = []

    try:
        g = Github(github_token)
        repo = g.get_repo(config_repo_name)
        config_content_file = repo.get_contents(config_file_path)
        config_content = config_content_file.decoded_content.decode('utf-8')
        start_urls_list = [url.strip() for url in config_content.strip().split('\n') if url.strip()]
        logging.info(f"从 GitHub 读取到 {len(start_urls_list)} 个起始 URL")
    except Exception as e:
        logging.error(f"无法从 GitHub 读取配置文件: {e}")
        start_urls_list = []

    max_pages_to_crawl = 10
    num_working_threads = 5
    main(start_urls_list, max_pages_to_crawl, num_working_threads, github_token=github_token)
