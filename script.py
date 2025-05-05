import os
import requests
from bs4 import BeautifulSoup
import time

# 配置
BASE_URL = 'https://t.me/dingyue_center'  
NEXT_PAGE_PARAM = 'page'  # 翻页参数名
DATA_DIR = 'data'
OUTPUT_FILE = os.path.join(DATA_DIR, 't.txt')

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

# 存储所有提取的链接
extracted_links = set()

def fetch_page(url, params=None):
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

def extract_links(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/api/' in href:
            links.add(href)
    return links

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
    page_number = 1
    has_next = True
    current_url = BASE_URL

    while has_next:
        print(f"正在抓取第{page_number}页内容...")
        html = fetch_page(current_url)
        if not html:
            break
        links = extract_links(html)
        print(f"找到 {len(links)} 个潜在链接。")
        for link in links:
            if link not in extracted_links:
                print(f"检测链接：{link}")
                if test_url(link):
                    print("链接有效，保存中...")
                    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                        f.write(link + '\n')
                    extracted_links.add(link)
                else:
                    print("链接失效，跳过。")
        # 翻页逻辑（请根据实际页面结构调整）
        # 这里假设有个“下一页”链接或参数
        # 例如，网址中增加页码参数
        page_number += 1
        # 如果没有下一页，可以通过分析html中的“下一页”元素来判断
        # 这里简化为计数，或自行实现检测逻辑
        # 你需要根据页面实际情况调整
        # 例如：
        # next_link = soup.find('a', text='下一页')
        # if next_link:
        #     current_url = next_link['href']
        # else:
        #     has_next = False
        # 为简化演示，假设有限页数
        if page_number > 50:
            has_next = False
        time.sleep(1)  # 礼貌性暂停

if __name__ == '__main__':
    main()
    print("抓取完成，结果已保存。")
