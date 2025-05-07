import os
import re
import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', '.') # 获取 GitHub 工作区路径，默认为当前目录
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, 'searched_links.txt') # 输出到新的文件
os.makedirs(DATA_DIR, exist_ok=True)

SEARCH_KEYWORDS = ['技术 订阅', 'VPN 订阅', '代理 订阅'] # 组合关键词进行搜索
SEARCH_ENGINE_BASE_URL = 'https://www.google.com/search'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def search_google(query, num_results=10):
    params = {'q': query, 'num': num_results}
    try:
        response = requests.get(SEARCH_ENGINE_BASE_URL, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Google 搜索失败，关键词: '{query}': {e}")
        return None

def extract_links_from_search_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # 清理 Google 搜索结果中的包装链接
        if href.startswith('/url?q='):
            href = href.split('/url?q=')[1].split('&')[0]
        if href.startswith('http') and 'google' not in href and 'telegram' not in href.lower():
            links.add(href)
    return list(links)

def main():
    all_found_links = set()
    for keyword in SEARCH_KEYWORDS:
        search_query = f"site:t.me {keyword}" # 搜索 t.me 域名下包含关键词的页面
        logging.info(f"正在搜索: {search_query}")
        search_results_html = search_google(search_query)
        if search_results_html:
            extracted_links = extract_links_from_search_results(search_results_html)
            for link in extracted_links:
                all_found_links.add(link)
                logging.info(f"找到潜在链接: {link}")

    if all_found_links:
        with open(OUTPUT_VALID_FILE, 'w', encoding='utf-8') as f:
            for link in sorted(list(all_found_links)):
                f.write(link + '\n')
        logging.info(f"找到 {len(all_found_links)} 个潜在链接并已保存到 {OUTPUT_VALID_FILE}")
        print(f"找到 {len(all_found_links)} 个潜在链接并已保存到 {OUTPUT_VALID_FILE}")
    else:
        logging.info("未找到符合条件的潜在链接。")
        print("未找到符合条件的潜在链接。")

if __name__ == '__main__':
    main()
