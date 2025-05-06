import os
import re
import logging
import configparser
from urllib.parse import urljoin
from pyppeteer import launch
from bs4 import BeautifulSoup
import asyncio
import time
import concurrent.futures

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 读取配置
config = configparser.ConfigParser()
config.read('config.ini')

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', '.') # 获取 GitHub 工作区路径，默认为当前目录
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_valid_file', fallback='valid_links.txt'))
OUTPUT_INVALID_FILE = os.path.join(DATA_DIR, config.get('settings', 'output_invalid_file', fallback='invalid_links.txt'))
MAX_PAGES = int(config.get('settings', 'max_pages', fallback='10')) # 提供默认值
MAX_WORKERS = int(config.get('settings', 'max_workers', fallback='5')) # 提供默认值
BASE_URL = config.get('settings', 'base_url')

excluded_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.xml', '.css', '.js')

async def extract_all_links_pyppeteer(page, base_url):
    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')
    links = set()
    keywords = ['/api/', 'oken=', '/s/']

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        absolute_url = urljoin(base_url, href)
        if absolute_url.startswith('http') and not absolute_url.startswith('https://t.me') and not absolute_url.endswith(excluded_extensions):
            for keyword in keywords:
                if keyword in absolute_url:
                    links.add(absolute_url)
                    break

    # 直接在页面内容中搜索符合模式的链接
    pattern = r'(https?://[^\s\'"<>]*(/api/[^\s\'"<>]*(?:\?[^\s\'"<>]+)?|oken=[^\s\'"<>]*(?:\?[^\s\'"<>]+)?|/s/[^\s\'"<>]*))'
    found_links = re.findall(pattern, content)
    for link_tuple in found_links:
        link = link_tuple[0]
        if not link.startswith('https://t.me') and not link.endswith(excluded_extensions):
            links.add(link)

    return list(links)

async def test_url_pyppeteer(url):
    try:
        browser = await launch(headless=True)
        page = await browser.newPage()
        response = await page.goto(url, timeout=30000)
        await browser.close()
        return response is not None and response.status == 200
    except Exception as e:
        logging.debug(f"测试链接失败 {url}: {e}")
        return False

def process_link(link):
    async def _process(link):
        if await test_url_pyppeteer(link):
            try:
                with open(OUTPUT_VALID_FILE, 'a', encoding='utf-8') as f:
                    f.write(link + '\n')
                logging.info(f"有效链接 (Pyppeteer测试通过): {link}")
                print(f"有效链接 (Pyppeteer测试通过): {link}")
            except Exception as e:
                logging.error(f"写入有效链接文件失败 {OUTPUT_VALID_FILE}: {e}")
        else:
            try:
                with open(OUTPUT_INVALID_FILE, 'a', encoding='utf-8') as f:
                    f.write(link + '\n')
                logging.info(f"无效链接 (Pyppeteer测试失败): {link}")
                print(f"无效链接 (Pyppeteer测试失败): {link}")
            except Exception as e:
                logging.error(f"写入无效链接文件失败 {OUTPUT_INVALID_FILE}: {e}")
    asyncio.run(_process(link))

async def main():
    logging.info(f"DATA_DIR is: {DATA_DIR}")
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(OUTPUT_VALID_FILE):
        with open(OUTPUT_VALID_FILE, 'w') as f:
            pass
    if not os.path.exists(OUTPUT_INVALID_FILE):
        with open(OUTPUT_INVALID_FILE, 'w') as f:
            pass

    current_url = BASE_URL
    collected_links = set()
    page_count = 0

    try:
        browser = await launch(headless=True)
        page = await browser.newPage()

        while current_url and page_count < MAX_PAGES:
            logging.info(f"使用 Pyppeteer 抓取页面：{current_url}")
            try:
                await page.goto(current_url, timeout=30000)
                await asyncio.sleep(5) # 等待页面加载完成

                links = await extract_all_links_pyppeteer(page, current_url)
                logging.info(f"使用 Pyppeteer 在页面上找到 {len(links)} 个非t.me链接。")

                new_links = [link for link in links if link not in collected_links]
                collected_links.update(new_links)

                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    executor.map(process_link, new_links)

                page_count += 1
                if page_count < MAX_PAGES:
                    # 模拟向下滚动加载更多内容
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(5)
                else:
                    break

            except Exception as e:
                logging.error(f"Pyppeteer 抓取页面 {current_url} 失败: {e}")
                break

    except Exception as e:
        logging.error(f"初始化 Pyppeteer 失败: {e}")
    finally:
        if 'browser' in locals() and browser:
            await browser.close()

    logging.info(f"全部完成，共使用 Pyppeteer 抓取到 {len(collected_links)} 个非t.me链接。")

if __name__ == '__main__':
    asyncio.run(main())
