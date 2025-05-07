import os
import re
import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', '.') # 获取 GitHub 工作区路径，默认为当前目录
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, 'searched_links.txt') # 输出到新的文件
os.makedirs(DATA_DIR, exist_ok=True)

SEARCH_KEYWORDS = ['/api/v1/client/subscribe?token=', 'token=', '/s/']
SEARCH_ENGINES = {
    'google': 'https://www.google.com/search',
    'duckduckgo': 'https://duckduckgo.com/html/',
    'bing': 'https://www.bing.com/search',
    'yandex': 'https://yandex.com/search/',
    'yahoo': 'https://search.yahoo.com/search'
}
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.google.com/'
}
REQUEST_DELAY = 1 # 设置请求延迟 (秒)

def search(engine_name, base_url, query, num_results=5):
    params = {}
    if engine_name == 'google':
        params = {'q': query, 'num': num_results}
    elif engine_name == 'duckduckgo':
        params = {'q': query}
    elif engine_name == 'bing':
        params = {'q': query, 'count': num_results}
    elif engine_name == 'yandex':
        params = {'text': query, 'lr': 213} # lr=213 for China, may need adjustment
    elif engine_name == 'yahoo':
        params = {'p': query, 'n': num_results}

    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(base_url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"{engine_name.capitalize()} 搜索失败，关键词: '{query}': {e}")
        return None

def extract_links_from_google_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('/url?q='):
            href = href.split('/url?q=')[1].split('&')[0]
        if href.startswith('http') and 'google' not in href:
            links.add(href)
    return list(links)

def extract_links_from_duckduckgo_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', class_='result__a', href=True):
        href = link['href']
        if href.startswith('http') and 'duckduckgo' not in href.lower():
            links.add(href)
    return list(links)

def extract_links_from_bing_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', {'class': 'b_algo'}): # Adjust class if needed
        href = link.get('href')
        if href and href.startswith('http') and 'bing' not in href.lower():
            links.add(href)
    return list(links)

def extract_links_from_yandex_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', {'class': 'Link', 'data-stat': 'search-result__title'}): # Adjust class and data-stat if needed
        href = link.get('href')
        if href and href.startswith('http') and 'yandex' not in href.lower():
            links.add(href)
    return list(links)

def extract_links_from_yahoo_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for link in soup.find_all('a', class_='js-algo-title', href=True): # Adjust class if needed
        href = link['href']
        if href.startswith('http') and 'yahoo' not in href.lower():
            links.add(href)
    return list(links)

def extract_links_from_page_content(html, keywords):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('http') and 'telegram' not in href.lower() and any(keyword in href for keyword in keywords):
            links.add(href)
    return list(links)

def browse_page(url):
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"浏览页面失败 {url}: {e}")
        return None

def main():
    all_found_links = set()
    for keyword in SEARCH_KEYWORDS:
        for engine_name, base_url in SEARCH_ENGINES.items():
            logging.info(f"正在使用 {engine_name.capitalize()} 搜索: {keyword}")
            search_results_html = search(engine_name, base_url, keyword)
            if search_results_html:
                search_result_links = []
                if engine_name == 'google':
                    search_result_links = extract_links_from_google_results(search_results_html)
                elif engine_name == 'duckduckgo':
                    search_result_links = extract_links_from_duckduckgo_results(search_results_html)
                elif engine_name == 'bing':
                    search_result_links = extract_links_from_bing_results(search_results_html)
                elif engine_name == 'yandex':
                    search_result_links = extract_links_from_yandex_results(search_results_html)
                elif engine_name == 'yahoo':
                    search_result_links = extract_links_from_yahoo_results(search_results_html)

                for search_result_link in search_result_links:
                    logging.info(f"正在浏览 {engine_name.capitalize()} 搜索结果页面: {search_result_link}")
                    page_content = browse_page(search_result_link)
                    if page_content:
                        extracted_links = extract_links_from_page_content(page_content, SEARCH_KEYWORDS)
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
