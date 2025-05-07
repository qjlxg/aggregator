import requests
from bs4 import BeautifulSoup
import re

CHANNEL_URL = 'https://t.me/s/dingyue_center'  # 频道网页版
OUTPUT_FILE = 'data/subscribes.txt'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; GitHubAction/1.0)'
}

def fetch_channel_pages():
    # Telegram 频道网页版只显示有限消息，示例仅拿第一页内容
    resp = requests.get(CHANNEL_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.text

def extract_links(html):
    soup = BeautifulSoup(html, 'html.parser')
    # Telegram频道中所有链接
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        # 过滤 t.me 开头的网址，保留其他网址
        if not href.startswith('https://t.me') and not href.startswith('http://t.me') and re.match(r'https?://', href):
            links.add(href)
    return links

def is_link_valid(url):
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        if r.status_code == 200:
            return True
    except Exception:
        return False
    return False

def load_existing_links():
    try:
        with open(OUTPUT_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def main():
    html = fetch_channel_pages()
    new_links = extract_links(html)
    existing_links = load_existing_links()
    all_links = existing_links.union(new_links)

    # 测试所有新链接有效性，只测试新增的，过滤已存在的
    valid_links = set()
    for link in new_links:
        if link not in existing_links:
            if is_link_valid(link):
                valid_links.add(link)
    if not valid_links:
        print('无有效新链接。')
        return

    # 追加有效新链接到文件（避免重复）
    with open(OUTPUT_FILE, 'a') as f:
        for link in sorted(valid_links):
            f.write(link + '\n')
    print(f'追加有效链接数量：{len(valid_links)}')

if __name__ == '__main__':
    main()
