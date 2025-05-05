import os
import re
import requests
from bs4 import BeautifulSoup
import time

BASE_URL = 'https://t.me/s/dingyue_center'  # 确保是 /s/ 格式的链接
DATA_DIR = 'data'
OUTPUT_FILE = os.path.join(DATA_DIR, 'all_links.txt')
MAX_PAGES = 50

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

def extract_all_links(html):
    pattern = r'https?://[^\s\'"<>]+'
    all_urls = re.findall(pattern, html)
    return all_urls

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 200
    except:
        return False

def get_next_page_url(html, current_url):
    soup = BeautifulSoup(html, 'html.parser')
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        next_url = 'https://t.me' + next_page['href']
        return next_url
    return None

def main():
    current_url = BASE_URL
    collected_links = set()
    page_count = 0

    os.makedirs(DATA_DIR, exist_ok=True)

    while current_url and page_count < MAX_PAGES:
        print(f"抓取页面：{current_url}")
        html = fetch_page(current_url)
        if not html:
            break

        links = extract_all_links(html)
        print(f"找到 {len(links)} 个链接。")

        for link in links:
            if link not in collected_links:
                if test_url(link):
                    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                        f.write(link + '\n')
                    collected_links.add(link)
                    print(f"有效链接：{link}")
                else:
                    print(f"无效链接：{link}")
                time.sleep(0.5)

        current_url = get_next_page_url(html, current_url)
        page_count += 1
        time.sleep(1)

    print(f"全部完成，共抓取到 {len(collected_links)} 个有效链接。")

    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w') as f:
            pass  # 创建空文件

if __name__ == '__main__':
    main()
