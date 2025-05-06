import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import logging
import concurrent.futures

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 获取 Telegram 频道页面的 HTML 内容
def fetch_page(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            content = page.content()
            browser.close()
        return content
    except Exception as e:
        logging.error(f"获取页面内容失败 {url}: {e}")
        return None

# 提取非 t.me 的链接并去重
def extract_links(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()  # 使用 set 去重
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and not href.startswith('https://t.me'):
            links.add(href)
    return links

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
    url = 'https://t.me/s/jichang_list'  # 使用 /s/ 访问公开频道内容
    html = fetch_page(url)
    if not html:
        logging.error("无法获取页面内容，退出程序")
        return

    # 提取非 t.me 的链接
    links = extract_links(html)
    logging.info(f"找到 {len(links)} 个非 t.me 链接")

    # 测试链接并保存有效链接
    valid_links = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(test_url, link): link for link in links}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if future.result():
                    valid_links.append(url)
            except Exception as e:
                logging.error(f"处理链接失败 {url}: {e}")

    # 确保 data 目录存在并保存结果
    os.makedirs('data', exist_ok=True)
    with open('data/ji.txt', 'w', encoding='utf-8') as f:
        for link in valid_links:
            f.write(link + '\n')

    logging.info(f"保存了 {len(valid_links)} 个有效链接到 data/ji.txt")

if __name__ == '__main__':
    main()
