import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import logging
import concurrent.futures

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置参数
BASE_URL = 'https://t.me/s/jichang_list'
OUTPUT_FILE = 'data/ji.txt'
MAX_PAGES = 50  # 抓取至少50个页面
MAX_WORKERS = 10  # 并发测试链接的最大线程数

# 获取 Telegram 页面内容
def fetch_page(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_load_state('networkidle')  # 等待页面加载完成
            content = page.content()
            browser.close()
        return content
    except Exception as e:
        logging.error(f"获取页面内容失败 {url}: {e}")
        return None

# 提取非 t.me 的链接
def extract_links(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()  # 使用 set 去重
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and not href.startswith('https://t.me'):
            links.add(href)
    return links

# 获取下一页链接
def get_next_page_url(html):
    soup = BeautifulSoup(html, 'html.parser')
    next_page = soup.find('a', attrs={'data-nav': 'next'})
    if next_page and 'href' in next_page.attrs:
        return 'https://t.me' + next_page['href']
    return None

# 测试链接是否可以连接
def test_url(url):
    try:
        r = requests.get(url, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

# 主函数
def main():
    # 创建输出目录
    os.makedirs('data', exist_ok=True)

    current_url = BASE_URL
    collected_links = set()  # 存储所有非 t.me 链接
    page_count = 0

    # 抓取至少50个页面
    while current_url and page_count < MAX_PAGES:
        logging.info(f"正在抓取第 {page_count + 1} 页：{current_url}")
        html = fetch_page(current_url)
        if not html:
            logging.error(f"页面 {current_url} 获取失败，停止抓取")
            break

        # 提取链接并去重
        links = extract_links(html)
        logging.info(f"第 {page_count + 1} 页找到 {len(links)} 个非 t.me 链接")
        collected_links.update(links)

        # 获取下一页链接
        current_url = get_next_page_url(html)
        page_count += 1

    logging.info(f"总共抓取 {page_count} 个页面，发现 {len(collected_links)} 个唯一非 t.me 链接")

    # 测试链接有效性
    valid_links = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(test_url, link): link for link in collected_links}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if future.result():
                    valid_links.append(url)
                    logging.info(f"有效链接：{url}")
            except Exception as e:
                logging.error(f"测试链接失败 {url}: {e}")

    # 保存有效链接到文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for link in valid_links:
            f.write(link + '\n')
    logging.info(f"保存了 {len(valid_links)} 个有效链接到 {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
