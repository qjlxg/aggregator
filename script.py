import os
import re
import requests
from bs4 import BeautifulSoup
import time

# 配置
BASE_URL = 'https://t.me/dingyue_center'  
DATA_DIR = 'data'
OUTPUT_FILE = os.path.join(DATA_DIR, 't.txt')

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

def extract_urls(html):
    # 使用正则表达式提取所有HTTP/HTTPS链接
    pattern = r'https?://[^\s\'"<>]+'
    urls = re.findall(pattern, html)
    return set(urls)

def test_url(url):
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return True
        else:
            return False
    except:
        return False

def main():
    html = fetch_page(BASE_URL)
    if not html:
        print("网页抓取失败")
        return

    # 提取所有链接
    all_links = extract_urls(html)
    print(f"找到 {len(all_links)} 个链接。")

    # 过滤和测试
    unique_links = set()
    for link in all_links:
        if link not in unique_links:
            print(f"检测链接：{link}")
            if test_url(link):
                print("链接有效，保存中...")
                with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                    f.write(link + '\n')
                unique_links.add(link)
            else:
                print("链接失效，跳过。")
            time.sleep(0.5)  # 避免请求过快

if __name__ == '__main__':
    main()
    print("全部完成。")
