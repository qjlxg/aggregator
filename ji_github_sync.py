import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import base64

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GITHUB_API_URL = "https://api.github.com"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version=14.0 Mobile/15E148 Safari/604.1'
]

def get_required_env_vars():
    config = {}
    required_vars = [
        'REPO_OWNER',
        'REPO_NAME',
        'GIT_BRANCH',
        'CONFIG_PATH',
        'SUBSCRIBES_PATH',
        'BOT'
    ]
    for var_name in required_vars:
        value = os.getenv(var_name)
        if not value:
            logging.error(f"缺少必需的环境变量: {var_name}")
            if var_name != 'BOT':
                 return None
            else:
                config[var_name] = None
        else:
             config[var_name] = value

    if config.get('BOT') is None:
         return None

    return config


def fetch_github_file_content(token, repo_owner, repo_name, file_path, branch):
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{file_path}?ref={branch}"
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        sha = data['sha']
        logging.info(f"成功获取文件内容: {file_path}")
        return content, sha
    except requests.exceptions.RequestException as e:
        if response.response is not None and response.response.status_code == 404:
             logging.info(f"文件 {file_path} 未找到 (404)。这对于结果文件可能是正常的。")
        else:
             logging.error(f"从 GitHub 获取文件 {file_path} 失败: {e}")
             try:
                 if response.response is not None:
                    logging.error(f"响应体: {response.response.json()}")
                 else:
                    logging.error("无法获取响应体。")
             except:
                 pass
        return None, None
    except Exception as e:
        logging.error(f"处理 GitHub 文件获取响应时发生错误: {e}")
        return None, None

def update_github_file_content(token, repo_owner, repo_name, file_path, new_content, sha, branch, commit_message):
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }
    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    try:
        response = requests.put(url, headers=headers, json=payload)
        response.raise_for_status()
        logging.info(f"成功在 GitHub 上更新文件: {file_path}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"在 GitHub 上更新文件 {file_path} 失败: {e}")
        try:
            if response.response is not None:
                error_details = response.response.json()
                logging.error(f"GitHub API 错误细节: {error_details}")
            else:
                logging.error("无法获取响应体。")
        except:
            pass
        return False
    except Exception as e:
        logging.error(f"在 GitHub 文件更新期间发生错误: {e}")
        return False

def is_valid_hostname(hostname):
    if not hostname or len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]
    allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(label) for label in hostname.split("."))

def is_valid_url(url):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    if not is_valid_hostname(parsed.netloc):
        return False
    if parsed.netloc == 't.me':
         return False
    return True

def clean_url(url):
    while url and url[-1] in '.,;:!?)':
        url = url[:-1]
    return url

def get_specific_urls_from_html(html, token_patterns):
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

    for target in targets:
        for a_tag in target.find_all('a', href=True):
            href = clean_url(a_tag['href'].rstrip('/'))
            if is_valid_url(href) and any(pattern in href for pattern in token_patterns):
                urls.add(href)
            else:
                logging.debug(f"从 <a> 标签丢弃 URL (模式/有效性不匹配): {href}")

        text = target.get_text(separator=' ', strip=True)
        found_potential_urls = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text)
        for url_in_text in found_potential_urls:
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text
            url_in_text = clean_url(url_in_text.rstrip('/'))
            if is_valid_url(url_in_text) and any(pattern in url_in_text for pattern in token_patterns):
                 urls.add(url_in_text)
            else:
                 logging.debug(f"从文本丢弃 URL (模式/有效性不匹配): {url_in_text}")

    return list(urls)

def test_url_connectivity(url, timeout=10):
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return 200 <= response.status_code < 300
    except requests.exceptions.RequestException as e:
        logging.debug(f"URL {url} 连接测试失败: {e}")
        return False

def get_next_page_url(html):
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more and load_more.has_attr('href'):
        return 'https://t.me' + load_more['href']
    return None

def fetch_page(url, timeout=15, max_retries=3):
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"尝试 {attempt + 1}/{max_retries} 次获取 {url} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 12 + attempt * 5))
            else:
                logging.error(f"在 {max_retries} 次尝试后获取 {url} 失败")
                return None
    return None

def main(max_pages_per_source=90, max_workers=20):
    config = get_required_env_vars()
    if not config:
        return

    github_token = config['BOT']
    repo_owner = config['REPO_OWNER']
    repo_name = config['REPO_NAME']
    branch = config['GIT_BRANCH']
    config_path = config['CONFIG_PATH']
    subscribes_path = config['SUBSCRIBES_PATH']

    logging.info(f"尝试从 {repo_owner}/{repo_name}/{config_path} 读取配置 (起始 URL 和查找模式)")
    config_content, _ = fetch_github_file_content(
        github_token, repo_owner, repo_name, config_path, branch
    )

    if not config_content:
        logging.error("从 GitHub 的 config.txt 读取失败。无法继续。")
        return

    start_urls = []
    token_patterns_list = []
    for line in config_content.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('#'):
            continue

        pattern_prefix = 'pattern='
        if stripped_line.startswith(pattern_prefix):
            pattern = stripped_line[len(pattern_prefix):].strip()
            if pattern:
                token_patterns_list.append(pattern)
                logging.debug(f"找到查找模式: {pattern}")
        else:
            start_urls.append(stripped_line)
            logging.debug(f"找到起始 URL: {stripped_line}")

    if not start_urls:
        logging.warning("GitHub config.txt 文件中没有找到起始 URL。无需爬取。")
        return

    if not token_patterns_list:
         logging.error("GitHub config.txt 文件中没有找到任何查找模式 (pattern=...)。无法进行链接提取。")
         return

    logging.info(f"成功读取 {len(start_urls)} 个起始 URL 和 {len(token_patterns_list)} 个查找模式。")

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
                time.sleep(random.uniform(15, 30))
            else:
                logging.info(f"源 {base_url} 没有找到更多页面。")
                current_url = None

        logging.info(f"======== 结束爬取源: {base_url}, 已处理 {page_count_for_source} 页面 ========")

    logging.info(f"\n======== 所有源爬取完毕，总页面数: {processed_page_count_total} ========")
    logging.info(f"在测试连通性前找到的总唯一特定 URL 数: {len(overall_found_specific_urls)}")

    urls_to_test = overall_found_specific_urls

    if not urls_to_test:
         logging.info("没有需要测试连通性的 URL。")
         valid_specific_urls = set()
    else:
        logging.info("开始并发 URL 连通性测试...")
        valid_specific_urls = set()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(test_url_connectivity, url): url for url in urls_to_test}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    is_connectable = future.result()
                    if is_connectable:
                        valid_specific_urls.add(url)
                    else:
                        logging.debug(f"URL {url} 不可连接.")
                except Exception as exc:
                    logging.error(f"URL {url} 在测试期间发生异常: {exc}")

        logging.info(f"连通性测试完成。找到的有效特定 URL 数: {len(valid_specific_urls)}")

    logging.info(f"尝试从 {repo_owner}/{repo_name}/{subscribes_path} 读取现有 URL")
    existing_subscribes_content, subscribes_sha = fetch_github_file_content(
        github_token, repo_owner, repo_name, subscribes_path, branch
    )

    existing_urls = set()
    if existing_subscribes_content:
        existing_urls = set(line.strip() for line in existing_subscribes_content.splitlines() if line.strip())
        logging.info(f"从 subscribes.txt 读取到 {len(existing_urls)} 个现有 URL。")
    else:
        logging.info(f"GitHub 上未找到 subscribes.txt 或为空。开始合并时使用空列表。")

    combined_urls = existing_urls.union(valid_specific_urls)

    if not combined_urls:
         logging.info("没有找到任何有效 URL (新的或现有的) 可供保存。")
         new_subscribes_content = ""
    else:
        sorted_combined_urls = sorted(list(combined_urls))
        new_subscribes_content = "\n".join(sorted_combined_urls) + "\n"

    logging.info(f"合并去重后的 URL 总数: {len(combined_urls)}")
    if existing_subscribes_content is not None:
         newly_added_count = len(valid_specific_urls) - len(valid_specific_urls.intersection(existing_urls))
         logging.info(f"本次运行新添加的有效 URL 数 (去重后): {newly_added_count}")
         commit_message = f"更新订阅列表 - 新增 {newly_added_count} 个唯一 URL"
    else:
         newly_added_count = len(combined_urls)
         logging.info(f"本次运行新添加的有效 URL 数 (首次保存): {newly_added_count}")
         commit_message = f"首次创建订阅列表 - 共 {newly_added_count} 个 URL"

    logging.info(f"尝试将更新后的 URL 写入 {repo_owner}/{repo_name}/{subscribes_path}")

    if update_github_file_content(
        github_token,
        repo_owner,
        repo_name,
        subscribes_path,
        new_subscribes_content,
        subscribes_sha,
        branch,
        commit_message
    ):
        logging.info("最终的订阅列表已成功保存到 GitHub。")
    else:
        logging.error("未能将最终订阅列表保存到 GitHub。")

if __name__ == '__main__':
    max_pages_per_source = 5
    max_workers = 20

    main(max_pages_per_source, max_workers)
