import os
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', '.') # 获取 GitHub 工作区路径，默认为当前目录
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_VALID_FILE = os.path.join(DATA_DIR, 'searched_links.txt') # 输出到新的文件
os.makedirs(DATA_DIR, exist_ok=True)

SEARCH_KEYWORDS = ['/api/v1/client/subscribe?token=', 'token=', '/s/']
SEARCH_ENGINES = {
    'google': 'https://www.google.com/'
}
SEARCH_DELAY = 2 # 搜索后等待时间 (秒)
SCROLL_PAUSE_TIME = 1 # 滚动加载等待时间 (秒)
NUM_SCROLLS = 3 # 滚动次数

def extract_links_selenium(driver, keywords):
    links = set()
    elements = driver.find_elements(By.TAG_NAME, 'a')
    for element in elements:
        href = element.get_attribute('href')
        if href and href.startswith('http') and 'telegram' not in href.lower() and any(keyword in href for keyword in keywords):
            links.add(href)
    return list(links)

def main():
    all_found_links = set()
    try:
        driver = uc.Chrome()
        for keyword in SEARCH_KEYWORDS:
            for engine_name, base_url in SEARCH_ENGINES.items():
                search_url = f"{base_url}search?q={keyword}"
                logging.info(f"使用 Selenium 在 {engine_name.capitalize()} 上搜索: {keyword}")
                driver.get(search_url)
                time.sleep(SEARCH_DELAY)

                # 模拟滚动加载更多结果
                body = driver.find_element(By.TAG_NAME, 'body')
                for _ in range(NUM_SCROLLS):
                    body.send_keys(Keys.PAGE_DOWN)
                    time.sleep(SCROLL_PAUSE_TIME)

                extracted_links = extract_links_selenium(driver, SEARCH_KEYWORDS)
                for link in extracted_links:
                    all_found_links.add(link)
                    logging.info(f"找到潜在链接: {link}")

    except Exception as e:
        logging.error(f"Selenium 过程中发生错误: {e}")
    finally:
        if 'driver' in locals() and driver:
            driver.quit()

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
