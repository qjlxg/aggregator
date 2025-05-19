# GitHub 同步订阅链接脚本 (ji_github_sync.py)

import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import base64 # 用于处理 GitHub API 的文件内容

# 配置日志输出为中文
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 需要从环境变量读取的配置项 ---
# 以下是脚本将尝试读取的环境变量名称。
# 请在 GitHub Actions Secrets 中创建同名密钥。
#
# REPO_OWNER: GitHub 仓库拥有者 (例如: qjlxg)
# REPO_NAME: GitHub 仓库名称 (例如: 362)
# GIT_BRANCH: GitHub 仓库分支 (例如: main)
# CONFIG_PATH: 配置文件的路径 (例如: data/config.txt)
# SUBSCRIBES_PATH: 结果文件的路径 (例如: data/subscribes.txt)
# BOT: GitHub Personal Access Token (需要 repo 权限)
# ---

GITHUB_API_URL = "https://api.github.com" # GitHub API 的固定地址

# User-Agent 池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version=14.0 Mobile/15E148 Safari/604.1'
]

# --- GitHub API 辅助函数 ---

def get_required_env_vars():
    """从环境变量获取所有必需的 GitHub 配置信息和令牌。"""
    config = {}
    # 脚本现在读取这些不以 GITHUB_ 开头的环境变量
    required_vars = [
        'REPO_OWNER',
        'REPO_NAME',
        'GIT_BRANCH', # 使用 GIT_BRANCH 避免冲突
        'CONFIG_PATH',
        'SUBSCRIBES_PATH',
        'BOT' # 令牌名称不变
    ]
    for var_name in required_vars:
        value = os.getenv(var_name)
        if not value:
            logging.error(f"缺少必需的环境变量: {var_name}")
            # 注意：BOT 令牌是最后一个，如果 BOT 缺失，错误信息会显示 BOT
            # 对于其他变量，可以直接在这里返回 None
            if var_name != 'BOT':
                 return None
            # 如果是 BOT 缺失，继续检查其他变量，最后返回 None
            else:
                config[var_name] = None # 先标记为 None
        else:
             config[var_name] = value

    # 再次检查 BOT 是否成功获取
    if config.get('BOT') is None:
         # 错误已经在循环中记录
         return None

    return config


def fetch_github_file_content(token, repo_owner, repo_name, file_path, branch):
    """从 GitHub 仓库获取文件内容和 SHA。"""
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{file_path}?ref={branch}"
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # 如果状态码不是 2xx，则抛出异常
        data = response.json()
        # 文件内容在 'content' 字段中是 Base64 编码的
        content = base64.b64decode(data['content']).decode('utf-8')
        sha = data['sha'] # 更新文件需要 SHA
        logging.info(f"成功获取文件内容: {file_path}")
        return content, sha
    except requests.exceptions.RequestException as e:
        # 特殊处理 404 Not Found 错误，结果文件首次运行可能不存在
        if response.response is not None and response.response.status_code == 404:
             logging.info(f"文件 {file_path} 未找到 (404)。这对于结果文件可能是正常的。")
        else:
             logging.error(f"从 GitHub 获取文件 {file_path} 失败: {e}")
             try: # 尝试打印响应体以获取更多非 404 错误的细节
                 if response.response is not None:
                    logging.error(f"响应体: {response.response.json()}")
                 else:
                    logging.error("无法获取响应体。")
             except:
                 pass # 忽略无法解析响应体的情况
        return None, None
    except Exception as e:
        logging.error(f"处理 GitHub 文件获取响应时发生错误: {e}")
        return None, None

def update_github_file_content(token, repo_owner, repo_name, file_path, new_content, sha, branch, commit_message):
    """在 GitHub 仓库中更新或创建文件内容。"""
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }
    # 新内容必须是 Base64 编码的
    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
        # 仅在更新现有文件时包含 SHA
    }
    if sha:
        payload["sha"] = sha
    # 注意: 如果 SHA 是 None，API 调用将尝试创建文件。

    try:
        response = requests.put(url, headers=headers, json=payload)
        response.raise_for_status() # 如果状态码不是 2xx，则抛出异常
        logging.info(f"成功在 GitHub 上更新文件: {file_path}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"在 GitHub 上更新文件 {file_path} 失败: {e}")
        try:
            # 尝试打印 GitHub API 错误细节 (如果可用)
            if response.response is not None:
                error_details = response.response.json()
                logging.error(f"GitHub API 错误细节: {error_details}")
            else:
                logging.error("无法获取响应体。")
        except:
            pass # 忽略无法解析错误细节的情况
        return False
    except Exception as e:
        logging.error(f"在 GitHub 文件更新期间发生错误: {e}")
        return False

# --- 现有爬取和验证函数 (翻译了注释和日志，并修改为接受模式列表) ---

def is_valid_hostname(hostname):
    """根据域名规则检查主机名是否有效。"""
    if not hostname or len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]
    allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(label) for label in hostname.split("."))

def is_valid_url(url):
    """通过检查结构和主机名验证 URL。"""
    # 排除 t.me 链接本身，因为我们从 t.me 爬取但不想要内部链接
    parsed = urlparse(url)
    # 需要协议和网络位置
    if not parsed.scheme or not parsed.netloc:
        return False
    # 只接受 http/https 协议
    if parsed.scheme not in ('http', 'https'):
        return False
    # 检查有效的主机名结构
    if not is_valid_hostname(parsed.netloc):
        return False
    # 如果网络位置是 t.me，则排除此链接
    if parsed.netloc == 't.me':
         return False
    return True

def clean_url(url):
    """移除 URL 末尾的标点符号。"""
    while url and url[-1] in '.,;:!?)':
        url = url[:-1]
    return url

# 修改函数签名，接受 token_patterns 列表作为参数
def get_specific_urls_from_html(html, token_patterns):
    """从 HTML 内容中提取包含特定 token 模式的 URL 并清理。"""
    if not token_patterns:
        logging.warning("未提供 token 模式列表，将无法提取特定 URL。")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set()
    # 定义我们要查找的模式 - 现在从参数传入

    for target in targets:
        # 从 <a> 标签中提取
        for a_tag in target.find_all('a', href=True):
            href = clean_url(a_tag['href'].rstrip('/'))
            # 检查它是否是有效的 URL 结构，并且包含任一 token 模式
            if is_valid_url(href) and any(pattern in href for pattern in token_patterns):
                urls.add(href)
            else:
                logging.debug(f"从 <a> 标签丢弃 URL (模式/有效性不匹配): {href}")

        # 从文本内容中提取
        text = target.get_text(separator=' ', strip=True)
        # 先使用更广泛的正则表达式查找潜在 URL，然后按模式和有效性过滤
        found_potential_urls = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text)
        for url_in_text in found_potential_urls:
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text
            url_in_text = clean_url(url_in_text.rstrip('/'))
            # 检查它是否是有效的 URL 结构，并且包含任一 token 模式
            if is_valid_url(url_in_text) and any(pattern in url_in_text for pattern in token_patterns):
                 urls.add(url_in_text)
            else:
                 logging.debug(f"从文本丢弃 URL (模式/有效性不匹配): {url_in_text}")

    return list(urls)

def test_url_connectivity(url, timeout=10):
    """通过尝试 HEAD 请求测试 URL 是否可连接。"""
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        # 使用 HEAD 请求更快，我们只需要状态码
        # allow_redirects=True 很重要，因为有些链接可能会重定向
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        # 检查成功的状态码 (200-299 范围)
        return 200 <= response.status_code < 300
    except requests.exceptions.RequestException as e:
        logging.debug(f"URL {url} 连接测试失败: {e}")
        return False

def get_next_page_url(html):
    """从 HTML 中提取下一页的 URL。"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more and load_more.has_attr('href'):
        # Telegram 相对路径需要与基本域名拼接
        return 'https://t.me' + load_more['href']
    return None

def fetch_page(url, timeout=15, max_retries=3):
    """带重试和随机 User-Agent 获取页面内容。"""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status() # 如果状态码是 4xx 或 5xx 则抛出异常
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"尝试 {attempt + 1}/{max_retries} 次获取 {url} 失败: {e}")
            if attempt < max_retries - 1:
                # 在后续重试时等待更长时间
                time.sleep(random.uniform(5, 12 + attempt * 5))
            else:
                logging.error(f"在 {max_retries} 次尝试后获取 {url} 失败")
                return None
    return None # 如果 max_retries > 0，通常不会执行到这里

# --- 主执行函数 ---

def main(max_pages_per_source=90, max_workers=20):
    """
    主函数控制整个流程:
    1. 从环境变量读取所有 GitHub 配置信息和令牌。
    2. 从私有 GitHub 仓库的 config.txt 读取起始 URL 和查找模式。
    3. 从 Telegram 频道爬取包含特定 token 的 URL。
    4. 测试找到的 URL 的连通性。
    5. 从私有 GitHub 仓库的 subscribes.txt 读取现有 URL。
    6. 合并、去重，并将新的有效 URL 追加到现有列表中。
    7. 将更新后的列表写回 GitHub 上的 subscribes.txt。
    """
    # 1. 获取必需的环境变量
    config = get_required_env_vars()
    if not config:
        # get_required_env_vars 中已记录错误消息
        return # 没有配置信息，无法继续

    github_token = config['BOT']
    # 从 config 字典中获取新的变量名对应的值
    repo_owner = config['REPO_OWNER']
    repo_name = config['REPO_NAME']
    branch = config['GIT_BRANCH']
    config_path = config['CONFIG_PATH']
    subscribes_path = config['SUBSCRIBES_PATH']


    # 2. 从 GitHub Config 读取起始 URL 和查找模式
    logging.info(f"尝试从 {repo_owner}/{repo_name}/{config_path} 读取配置 (起始 URL 和查找模式)")
    config_content, _ = fetch_github_file_content(
        github_token, repo_owner, repo_name, config_path, branch
    )

    if not config_content:
        logging.error("从 GitHub 的 config.txt 读取失败。无法继续。")
        return

    # 解析配置内容，提取起始 URL 和查找模式
    start_urls = []
    token_patterns_list = []
    for line in config_content.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('#'):
            continue # 跳过空行和注释

        # 检查是否是模式行
        pattern_prefix = 'pattern='
        if stripped_line.startswith(pattern_prefix):
            # 提取模式
            pattern = stripped_line[len(pattern_prefix):].strip()
            if pattern:
                token_patterns_list.append(pattern)
                logging.debug(f"找到查找模式: {pattern}")
        else:
            # 视为起始 URL
            start_urls.append(stripped_line)
            logging.debug(f"找到起始 URL: {stripped_line}")


    if not start_urls:
        logging.warning("GitHub config.txt 文件中没有找到起始 URL。无需爬取。")
        return

    if not token_patterns_list:
         logging.error("GitHub config.txt 文件中没有找到任何查找模式 (pattern=...)。无法进行链接提取。")
         return

    logging.info(f"成功读取 {len(start_urls)} 个起始 URL 和 {len(token_patterns_list)} 个查找模式。")


    # 3. 从 Telegram 频道爬取特定 URL
    overall_found_specific_urls = set()
    processed_page_count_total = 0

    for base_url in start_urls:
        logging.info(f"\n======== 开始爬取源: {base_url} ========")
        current_url = base_url
        page_count_for_source = 0

        while current_url and page_count_for_source < max_pages_per_source:
            logging.info(f"正在获取页面: {current_url} (源: {base_url}, 页面 {page_count_for_source + 1}/{max_pages_per_source})")
            html = fetch_page(current_url)
            if html is None:
                logging.warning(f"无法获取 {current_url} 的内容，停止爬取此源。")
                break

            # 使用修改后的函数只获取特定 token 的 URL，并传入模式列表
            new_specific_urls = get_specific_urls_from_html(html, token_patterns_list)

            if new_specific_urls:
                logging.info(f"在此页面找到 {len(new_specific_urls)} 个特定 URL。")
                overall_found_specific_urls.update(new_specific_urls)
                logging.info(f"迄今为止找到的总唯一特定 URL 数: {len(overall_found_specific_urls)}")
            else:
                 logging.info("在此页面没有找到新的特定 URL。")

            next_page_url = get_next_page_url(html)

            if next_page_url:
                current_url = next_page_url
                page_count_for_source += 1
                processed_page_count_total += 1
                # 在页面获取之间添加延迟，以礼貌待人
                time.sleep(random.uniform(15, 30))
            else:
                logging.info(f"源 {base_url} 没有找到更多页面。")
                current_url = None # 停止此源的循环

        logging.info(f"======== 结束爬取源: {base_url}, 已处理 {page_count_for_source} 页面 ========")

    logging.info(f"\n======== 所有源爬取完毕，总页面数: {processed_page_count_total} ========")
    logging.info(f"在测试连通性前找到的总唯一特定 URL 数: {len(overall_found_specific_urls)}")

    urls_to_test = overall_found_specific_urls # 需要测试连通性的 URL 集合


    # 4. 测试找到的 URL 的连通性
    if not urls_to_test:
         logging.info("没有需要测试连通性的 URL。")
         valid_specific_urls = set()
    else:
        logging.info("开始并发 URL 连通性测试...")
        valid_specific_urls = set() # 使用 set 方便直接添加和去重
        # 使用 ThreadPoolExecutor 进行并发测试
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 使用 as_completed 以便结果一完成就处理
            future_to_url = {executor.submit(test_url_connectivity, url): url for url in urls_to_test}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    is_connectable = future.result()
                    if is_connectable:
                        valid_specific_urls.add(url)
                        # logging.debug(f"URL {url} 可连接.") # 太冗长
                    else:
                        logging.debug(f"URL {url} 不可连接.")
                except Exception as exc:
                    logging.error(f"URL {url} 在测试期间发生异常: {exc}")

        logging.info(f"连通性测试完成。找到的有效特定 URL 数: {len(valid_specific_urls)}")

    # 5. 从 GitHub 读取现有结果文件
    logging.info(f"尝试从 {repo_owner}/{repo_name}/{subscribes_path} 读取现有 URL")
    existing_subscribes_content, subscribes_sha = fetch_github_file_content(
        github_token, repo_owner, repo_name, subscribes_path, branch
    )

    existing_urls = set()
    if existing_subscribes_content:
        # 将现有内容解析为 set，忽略空行
        existing_urls = set(line.strip() for line in existing_subscribes_content.splitlines() if line.strip())
        logging.info(f"从 subscribes.txt 读取到 {len(existing_urls)} 个现有 URL。")
    else:
        # subscribes_sha 将为 None，表示文件不存在或无法读取
        logging.info(f"GitHub 上未找到 subscribes.txt 或为空。开始合并时使用空列表。")


    # 6. 合并、去重并准备新内容
    # 合并现有有效 URL 和新找到的有效 URL
    combined_urls = existing_urls.union(valid_specific_urls) # Union 自动去重

    if not combined_urls:
         logging.info("没有找到任何有效 URL (新的或现有的) 可供保存。")
         # 如果订阅文件存在 SHA，传入空内容会清空文件；如果 SHA 为 None，传入空内容会尝试创建空文件。
         new_subscribes_content = ""
    else:
        # 对合并后的列表进行排序，以保持文件内容的一致性
        sorted_combined_urls = sorted(list(combined_urls))
        # 格式化为用于保存的内容 (每行一个 URL)
        new_subscribes_content = "\n".join(sorted_combined_urls) + "\n" # 确保末尾有换行

    logging.info(f"合并去重后的 URL 总数: {len(combined_urls)}")
    # 仅在成功读取现有文件时计算“新增”数量
    if existing_subscribes_content is not None: # 判断是否成功读取了现有文件 (即使为空内容)
         newly_added_count = len(valid_specific_urls) - len(valid_specific_urls.intersection(existing_urls))
         logging.info(f"本次运行新添加的有效 URL 数 (去重后): {newly_added_count}")
         commit_message = f"更新订阅列表 - 新增 {newly_added_count} 个唯一 URL"
    else:
         # 第一次创建文件的情况
         newly_added_count = len(combined_urls)
         logging.info(f"本次运行新添加的有效 URL 数 (首次保存): {newly_added_count}")
         commit_message = f"首次创建订阅列表 - 共 {newly_added_count} 个 URL"


    # 7. 将更新后的结果写回 GitHub
    logging.info(f"尝试将更新后的 URL 写入 {repo_owner}/{repo_name}/{subscribes_path}")


    if update_github_file_content(
        github_token,
        repo_owner,
        repo_name,
        subscribes_path,
        new_subscribes_content,
        subscribes_sha, # 如果文件不存在，这里是 None，会尝试创建文件
        branch,
        commit_message
    ):
        logging.info("最终的订阅列表已成功保存到 GitHub。")
    else:
        logging.error("未能将最终订阅列表保存到 GitHub。")


if __name__ == '__main__':
    # 爬取和测试的参数
    max_pages_to_crawl_per_source = 1 # 每个源最多爬取的页面数
    concurrent_workers = 20 # 并发连通性测试的线程数

    main(max_pages_per_source, concurrent_workers)
