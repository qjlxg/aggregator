import time
import re
import requests
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from collections import Counter

CHANNEL_URL = "https://t.me/s/dingyue_center"
OUTPUT_FILE = "data/subscribes.txt"
SCROLL_PAUSE_TIME = 2  # 等待页面加载秒数
MAX_SCROLLS = 30       # 最大滚动次数

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def scroll_to_bottom(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for i in range(MAX_SCROLLS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_links(driver):
    elems = driver.find_elements("tag name", "a")
    links = set()
    for a in elems:
        href = a.get_attribute("href")
        if href and href.startswith("http"):
            links.add(href)
    return links

def print_domains_stat(links):
    domains = [urlparse(link).netloc for link in links]
    counter = Counter(domains)
    print("="*40)
    print("抓取到链接的域名统计（域名: 数量）：")
    for domain, count in counter.most_common():
        print(f"{domain}: {count}")
    print("="*40)

    print("所有链接列表：")
    for link in sorted(links):
        print(link)
    print("="*40)

def is_link_valid(url):
    try:
        r = requests.get(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def load_existing_links():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def save_links(new_valid_links):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for link in sorted(new_valid_links):
            f.write(link + "\n")

def main():
    driver = init_driver()
    print(f"打开频道网页 {CHANNEL_URL} ...")
    driver.get(CHANNEL_URL)
    time.sleep(5)

    print("滚动页面加载更多消息...")
    scroll_to_bottom(driver)

    print("提取所有链接...")
    scraped_links = extract_links(driver)

    print_domains_stat(scraped_links)

    # 示例过滤，如果你想排除 t.me 和 telegram.org 可以在这里加过滤条件
    filtered_links = set(
        l for l in scraped_links if not l.startswith("https://t.me") and not l.startswith("http://t.me")
    )
    # 如果你还想排除 telegram.org，解开下面注释：
    # filtered_links = set(l for l in filtered_links if not l.startswith("https://telegram.org") and not l.startswith("http://telegram.org"))

    print(f"过滤后链接数量：{len(filtered_links)}")

    existing_links = load_existing_links()
    new_links = filtered_links - existing_links

    if not new_links:
        print("无有效新链接。")
        driver.quit()
        return

    print(f"新链接数量{len(new_links)}，开始测试有效性...")

    valid_links = set()
    for link in new_links:
        print(f"测试 {link} ...", end="")
        if is_link_valid(link):
            print("有效")
            valid_links.add(link)
        else:
            print("无效或超时")

    if valid_links:
        print(f"追加有效链接数量：{len(valid_links)} 到文件 {OUTPUT_FILE}")
        save_links(valid_links)
    else:
        print("无有效新链接")

    driver.quit()

if __name__ == "__main__":
    main()
