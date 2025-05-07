import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

CHANNEL_URL = "https://t.me/s/dingyue_center"
OUTPUT_FILE = "data/subscribes.txt"
SCROLL_PAUSE_TIME = 2  # 等待页面加载的时间（秒）
MAX_SCROLLS = 30       # 最大滚动次数，避免无限加载

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
            # 已经到底部了
            break
        last_height = new_height

def extract_links(driver):
    elems = driver.find_elements("tag name", "a")
    links = set()
    for a in elems:
        href = a.get_attribute("href")
        if href and href.startswith("http") and not href.startswith("https://t.me") and not href.startswith("http://t.me"):
            links.add(href)
    return links

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

    print(f"打开频道网页 {CHANNEL_URL}...")
    driver.get(CHANNEL_URL)
    time.sleep(5)  # 首次加载等待

    print("滚动页面加载更多消息...")
    scroll_to_bottom(driver)

    print("提取所有链接...")
    scraped_links = extract_links(driver)
    print(f"抓取到 {len(scraped_links)} 个链接（排除 t.me 开头）")

    existing_links = load_existing_links()
    new_links = scraped_links - existing_links

    if not new_links:
        print("没有新的链接需要处理")
        driver.quit()
        return

    print(f"新链接数量：{len(new_links)}，开始测试有效性...")

    valid_links = set()
    for link in new_links:
        print(f"测试 {link} ......", end="")
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
