import os
import re
import requests
from bs4 import BeautifulSoup
import time

# 配置信息
BASE_URL = 'https://t.me/dingyue_center'  # 替换为你的Telegram公开频道地址
DATA_DIR = 'data'
OUTPUT_FILE = os.path.join(DATA_DIR, 't.txt')
MAX_PAGES = 50  # 最大抓取页数，Telegram单次最多返回50条消息（大约2-3页）

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 请求头
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

def extract_links(html):
    pattern = r'https?://[^\s\'"<>]+'
    all_urls = re.findall(pattern, html)
    target_links = [url for url in all_urls if '/api/v1/client/subscribe?token=' in url]
    return target_links

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return True
        else:
            return False
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

    while current_url and page_count < MAX_PAGES:
        print(f"抓取页面：{current_url}")
        html = fetch_page(current_url)
        if not html:
            print("页面抓取失败，跳过。")
            break

        links = extract_links(html)
        print(f"找到 {len(links)} 个目标链接。")

        for link in links:
            if link not in collected_links:
                print(f"测试链接：{link}")
                if test_url(link):
                    print(f"链接有效，保存：{link}")
                    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                        f.write(link + '\n')
                    collected_links.add(link)
                else:
                    print(f"链接无效，跳过：{link}")
                time.sleep(0.5)  # 避免请求过快被限制

        # 获取下一页URL
        current_url = get_next_page_url(html, current_url)
        page_count += 1
        time.sleep(1)  # 适当的抓取间隔

    print(f"全部完成，共抓取到 {len(collected_links)} 个有效链接。")

if __name__ == '__main__':
    main()
