import requests  # 用于发送HTTP请求
from bs4 import BeautifulSoup  # 用于解析HTML内容
import re  # 用于正则表达式匹配
import time  # 用于时间相关操作（如延迟）
import random  # 用于生成随机数
import logging  # 用于记录日志信息
import os  # 用于访问环境变量
import threading # 用于多线程处理
from queue import Queue # 用于线程安全地传递数据

# 配置日志 (Configuring logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 请求头池 (User-Agent pool to avoid being blocked)
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

# 环境变量名 (Name of environment variables)
CONFIG_URL_ENV = "CONFIG_URL"
SUBSCRIBE_URL_ENV = "SUBSCRIBE_URL"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

def get_random_headers():
    """获取随机请求头 (Get a random User-Agent)"""
    return {'User-Agent': random.choice(USER_AGENTS)}


def is_valid_url(url):
    """判断URL是否有效 (Check if URL is valid, excluding Telegram URLs)"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)


def get_urls_from_html(html):
    """从HTML中提取URL (Extract URLs from HTML)"""
    soup = BeautifulSoup(html, 'html.parser') # 使用BeautifulSoup解析HTML
    targets = soup.find_all(class_=[ # 查找包含链接的特定类名的元素
        'tgme_widget_message_text', 'tgme_widget_message_photo',
        'tgme_widget_message_video', 'tgme_widget_message_document',
        'tgme_widget_message_poll'
    ])
    urls = set() # 使用集合去重
    for target in targets:
        text = target.get_text(separator=' ', strip=True) # 获取元素的文本内容
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text) # 使用正则表达式查找URL
        urls.update(url for url in found_urls if is_valid_url(url)) # 过滤无效URL并添加到集合
    return list(urls) # 将集合转换为列表


def test_url_connectivity(url, timeout=5):
    """测试URL是否可连通 (Test if a URL is reachable)"""
    try:
        response = requests.head(url, timeout=timeout) # 发送HEAD请求
        response.raise_for_status() # 检查HTTP状态码，如果不是200则抛出异常
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} 连接测试失败: {e}") # 记录警告信息
        return False


def get_next_page_url(html):
    """提取下一页URL (Extract the URL of the next page)"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more') # 查找下一页链接
    return 'https://t.me' + load_more['href'] if load_more else None  # 构建完整的下一页URL


def fetch_page(url, headers, timeout=10, max_retries=3):
    """抓取页面内容，带重试机制 (Fetch page content with retry mechanism)"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout) # 发送GET请求
            response.raise_for_status() # 检查HTTP状态码
            return response.text # 返回页面内容
        except requests.RequestException as e:
            logging.warning(f"抓取 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}") # 记录警告信息
            if attempt < max_retries - 1:
                time.sleep(random.uniform(38, 53)) # 随机延迟
            else:
                logging.error(f"抓取 {url} 失败，超出最大重试次数") # 记录错误信息
                return None

def get_start_urls_from_config(config_url):
    """从配置URL获取起始URL列表 (Get starting URLs from config URL)"""
    logging.info(f"Attempting to fetch config from URL: {config_url}") #调试：打印URL
    try:
        response = requests.get(config_url) # 发送GET请求
        response.raise_for_status() # 检查HTTP状态码
        return response.text.strip().splitlines() # 返回URL列表
    except requests.RequestException as e:
        logging.error(f"获取配置失败: {e}") # 记录错误信息
        return []

def save_urls_to_github(urls, repo_url, github_token):
    """保存URL到 GitHub 仓库，并隐藏链接 (Save URLs to GitHub repository and hide the link using GitHub API)"""
    try:
        # GitHub API 需要去掉 raw (GitHub API requires removing 'raw')
        api_url = repo_url.replace('/raw/refs/heads/main', '/contents/data/subscribes.txt') # 构建GitHub API URL
        headers = {
            "Authorization": f"token {github_token}", # 设置认证头
            "Accept": "application/vnd.github.v3+json" # 设置Accept头
        }

        # 获取现有文件内容和 sha 值 (Get existing file content and SHA value)
        get_response = requests.get(api_url, headers=headers)
        get_response.raise_for_status()
        existing_data = get_response.json()
        sha = existing_data['sha'] # 获取SHA值, 用于后续提交
        content = existing_data.get('content', '')
        if content:
            import base64
            content = base64.b64decode(content).decode('utf-8')  # Decode existing content

        updated_content = content + "\n".join(urls) + "\n" # Create updated content

        # Base64 编码新内容 (Base64 encode the updated content)
        import base64
        updated_content_encoded = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')

        # 构建更新请求 (Build the update request)
        data = {
            "message": "Add new URLs",  # 提交信息
            "content": updated_content_encoded, # Base64编码的内容
            "sha": sha, # SHA值
            "branch": "main" # 分支名
        }

        put_response = requests.put(api_url, headers=headers, json=data) # 发送PUT请求更新文件
        put_response.raise_for_status()
        logging.info("URL 已追加保存到 GitHub 仓库 (链接已隐藏).") # 记录信息

    except requests.RequestException as e:
        logging.error(f"保存到 GitHub 仓库失败: {e}") # 记录错误信息
    except KeyError as e:
        logging.error(f"解析 GitHub API 响应失败: {e}") # 记录错误信息


def crawl_single_source(start_url, headers, max_pages, url_queue):
    """抓取单个来源的URL (Crawl URLs from a single source)"""
    current_url = start_url
    page_count = 0
    while current_url and page_count < max_pages:
        logging.info(f"抓取: {current_url} (第 {page_count + 1}/{max_pages} 页，来源: {start_url})") # 记录信息
        html = fetch_page(current_url, headers) # 获取页面内容
        if html is None:
            break
        new_urls = get_urls_from_html(html) # 从页面中提取URL
        for url in new_urls:
            url_queue.put(url) # 将URL放入队列
        current_url = get_next_page_url(html) # 获取下一页URL
        page_count += 1
        time.sleep(random.uniform(35, 45))  # 随机延迟


def worker(url_queue, valid_urls, lock):
    """工作线程：验证URL (Worker thread: Validate URLs)"""
    while True:
        url = url_queue.get() # 从队列中获取URL
        if url is None:
            break
        if test_url_connectivity(url): # 测试URL连通性
            with lock: # 使用锁保证线程安全
                valid_urls.add(url) # 将有效URL添加到集合
        url_queue.task_done() # 标记任务完成


def main(config_url, subscribe_url, github_token, max_pages=10, num_threads=5):
    """主函数：多线程抓取 (Main function: Multi-threaded crawling)"""
    start_urls = get_start_urls_from_config(config_url) # 从配置URL获取起始URL列表
    if not start_urls:
        logging.error("未获取到起始 URL，程序终止。") # 记录错误信息
        return

    url_queue = Queue() # 创建URL队列
    valid_urls = set() # 创建有效URL集合
    lock = threading.Lock() # 创建锁

    # 创建URL验证线程 (Create URL validation threads)
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock)) # 创建线程
        t.start() # 启动线程
        threads.append(t) # 添加到线程列表

    # 创建爬取线程 (Create crawling threads)
    for start_url in start_urls:
        headers = get_random_headers() # 获取随机请求头
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, max_pages, url_queue)) # 创建线程
        t.start() # 启动线程
        threads.append(t) # 添加到线程列表

    # 等待爬取线程完成 (Wait for crawling threads to complete)
    for t in threads[num_threads:]:
        t.join() # 等待线程结束

    # 停止验证线程 (Stop validation threads)
    for _ in range(num_threads):
        url_queue.put(None) # 添加None到队列，作为线程结束的信号
    for t in threads[:num_threads]:
        t.join() # 等待线程结束

    logging.info(f"所有来源抓取完毕") # 记录信息
    logging.info(f"有效 URL 数量: {len(valid_urls)}") # 记录信息
    save_urls_to_github(list(valid_urls), subscribe_url, github_token) # 保存URL到GitHub


if __name__ == '__main__':
    config_url = os.environ.get(CONFIG_URL_ENV) # 从环境变量获取配置URL
    subscribe_url = os.environ.get(SUBSCRIBE_URL_ENV) # 从环境变量获取订阅URL
    github_token = os.environ.get(GITHUB_TOKEN_ENV)  # 从环境变量获取GitHub Token (Get GitHub Token from environment variable)

    if not config_url or not subscribe_url or not github_token:
        logging.error("请设置 CONFIG_URL, SUBSCRIBE_URL 和 GITHUB_TOKEN 环境变量。") # 记录错误信息
    else:
        max_pages_to_crawl = 10
        main(config_url, subscribe_url, github_token, max_pages_to_crawl) # 调用主函数
