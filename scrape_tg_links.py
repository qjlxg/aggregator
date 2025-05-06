import os
import re
import requests
from bs4 import BeautifulSoup
import time
import logging
import concurrent.futures
import base64

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量中获取配置
BASE_URL = os.environ.get('BASE_URL')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_OWNER = 'qjlxg'
REPO_NAME = '362'
FILE_PATH = 'data/subscribes.txt'

# 检查环境变量是否设置
if not BASE_URL or not GITHUB_TOKEN:
    logging.error("环境变量 BASE_URL 或 GITHUB_TOKEN 未设置")
    exit(1)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    """抓取页面内容"""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logging.error(f"请求失败 {url}: {e}")
        return None

def extract_all_links(html):
    """提取页面中的所有非 t.me 链接"""
    pattern = r'https?://[^\s\'"<>]+'
    all_links = re.findall(pattern, html)
    filtered_links = [link for link in all_links if not link.startswith('https://t.me')]
    return filtered_links

def test_url(url):
    """测试链接是否有效"""
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

def get_next_page_url(html, current_url):
    """获取下一页的 URL"""
    soup = BeautifulSoup(html, 'html.parser')
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        return 'https://t.me' + next_page['href']
    return None

def get_file_content():
    """从 GitHub 获取当前文件内容"""
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        content = response.json()['content']
        return base64.b64decode(content).decode('utf-8')
    else:
        logging.error(f"获取文件内容失败: {response.status_code}")
        return ''

def update_file_content(new_links):
    """将新链接追加到 GitHub 文件中"""
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        sha = response.json()['sha']
        content = response.json()['content']
        current_content = base64.b64decode(content).decode('utf-8')
    else:
        sha = None
        current_content = ''

    updated_content = current_content + '\n'.join(new_links) + '\n'
    encoded_content = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')

    data = {
        'message': 'Append new links',
        'content': encoded_content,
        'sha': sha if sha else None
    }

    response = requests.put(url, headers=headers, json=data)
    if response.status_code in (200, 201):
        logging.info("文件更新成功")
    else:
        logging.error(f"文件更新失败: {response.status_code}")

def process_link(link):
    """处理单个链接"""
    if link.startswith('https://t.me'):
        logging.info(f"跳过 t.me 链接：{link}")
        return None
    if test_url(link):
        logging.info(f"有效链接：{link}")
        return link
    else:
        logging.info(f"无效链接：{link}")
        return None

def main():
    current_url = BASE_URL
    collected_links = set()
    page_count = 0
    MAX_PAGES = 10
    MAX_WORKERS = 5

    while current_url and page_count < MAX_PAGES:
        logging.info(f"抓取页面：{current_url}")
        html = fetch_page(current_url)
        if not html:
            break

        links = extract_all_links(html)
        logging.info(f"找到 {len(links)} 个非 t.me 链接。")

        new_links = [link for link in links if link not in collected_links]
        collected_links.update(new_links)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            valid_links = list(filter(None, executor.map(process_link, new_links)))

        if valid_links:
            update_file_content(valid_links)

        current_url = get_next_page_url(html, current_url)
        page_count += 1
        time.sleep(1)

    logging.info(f"全部完成，共抓取到 {len(collected_links)} 个非 t.me 链接。")

if __name__ == '__main__':
    main()
