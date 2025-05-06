import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import logging
import concurrent.futures
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置参数
BASE_URL = 'https://t.me/s/jichang_list'
OUTPUT_FILE = 'data/ji.txt'
MAX_PAGES = 50  
MAX_WORKERS = 10  # 并发测试链接的最大线程数

def init_playwright():
    """
    初始化Playwright，返回浏览器实例。
    """
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    return p, browser

def close_playwright(p, browser):
    """
    关闭playwright和浏览器实例
    """
    browser.close()
    p.stop()

def fetch_page_content(browser, url):
    """
    使用已初始化的浏览器请求页面内容
    增加模拟“展开”按钮的点击逻辑。
    """
    try:
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state('networkidle', timeout=15000)  # 等待完全加载

        # 这里替换成你的“加载更多”按钮的选择器（如果存在）
        load_more_selector = '.load-more'  

        # 循环点击“加载更多”直到没有按钮
        while True:
            try:
                load_more_button = page.query_selector(load_more_selector)
                if load_more_button:
                    load_more_button.click()
                    # 等待内容加载
                    page.wait_for_load_state('networkidle', timeout=15000)
                    time.sleep(1)  # 等待内容加载完成
                else:
                    break
            except Exception:
                # 没有按钮或点击失败
                break

        content = page.content()
        page.close()
        return content
    except Exception as e:
        logging.error(f"获取页面内容失败 {url}: {e}")
        return None

def extract_links(html):
    """
    从页面源码中提取非t.me链接
    """
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and not href.startswith('https://t.me'):
            links.add(href)
    return links

def get_next_page_url(html):
    """
    获取下一页链接（可选，依赖页面结构）
    """
    soup = BeautifulSoup(html, 'html.parser')
    next_page_tag = soup.find('a', attrs={'data-nav': 'next'})
    if next_page_tag and 'href' in next_page_tag.attrs:
        href = next_page_tag['href']
        if not href.startswith('http'):
            return 'https://t.me' + href
        else:
            return href
    return None

def test_url(url):
    """
    测试链接是否有效
    """
    try:
        r = requests.get(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def main():
    os.makedirs('data', exist_ok=True)

    # 初始化playwright
    p, browser = init_playwright()

    current_url = BASE_URL
    collected_links = set()
    page_count = 0

    while current_url and page_count < MAX_PAGES:
        logging.info(f"正在抓取第 {page_count + 1} 页：{current_url}")
        html = fetch_page_content(browser, current_url)
        if not html:
            logging.error(f"页面 {current_url} 获取失败，停止抓取")
            break

        links = extract_links(html)
        logging.info(f"第 {page_count + 1} 页找到 {len(links)} 个非 t.me 链接")
        collected_links.update(links)

        # 获取下一页（根据实际页面结构调整）
        current_url = get_next_page_url(html)
        page_count += 1
        time.sleep(1)

    # 关闭playwright
    close_playwright(p, browser)

    logging.info(f"总共抓取 {page_count} 个页面，发现 {len(collected_links)} 个唯一非 t.me 链接")

    # 并发测试链接
    valid_links = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(test_url, url): url for url in collected_links}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if future.result():
                    valid_links.append(url)
                    logging.info(f"有效链接：{url}")
            except Exception:
                pass

    # 保存到文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for url in valid_links:
            f.write(url + '\n')
    logging.info(f"保存了 {len(valid_links)} 个有效链接到 {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
