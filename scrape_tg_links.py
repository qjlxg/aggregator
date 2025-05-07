from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import re
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_links_selenium_with_scroll(url, keywords, scroll_pause_time=2, num_scrolls=5):
    """
    使用 Selenium 抓取页面，滚动加载更多内容，并提取包含特定关键词的外部链接。

    Args:
        url (str): 目标 URL。
        keywords (list): 需要包含在链接中的关键词列表。
        scroll_pause_time (int): 每次滚动后暂停的时间（秒）。
        num_scrolls (int): 滚动的次数。
    Returns:
        list: 包含符合条件的外部链接的列表。
    """
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    driver.get(url)
    time.sleep(5) # 初始等待页面加载

    links = set()
    body = driver.find_element(By.TAG_NAME, 'body')

    try:
        for _ in range(num_scrolls):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(scroll_pause_time)
            logging.info(f"滚动页面 {_ + 1}/{num_scrolls}")

            elements = driver.find_elements(By.TAG_NAME, 'a')
            for element in elements:
                href = element.get_attribute('href')
                if href and href.startswith('http') and not href.startswith('https://t.me'):
                    for keyword in keywords:
                        if keyword in href:
                            links.add(href)
                            break
    except Exception as e:
        logging.error(f"滚动或链接提取过程中发生错误: {e}")
    finally:
        driver.quit()

    return list(links)

if __name__ == '__main__':
    target_url = "https://t.me/s/dingyue_center"
    keywords = ['/api/', 'oken=', '/s/']
    scroll_pause = 3 # 增加滚动暂停时间
    num_scroll = 10 # 增加滚动次数
    external_links = extract_links_selenium_with_scroll(target_url, keywords, scroll_pause, num_scroll)

    logging.info(f"找到 {len(external_links)} 个符合条件的外部链接：")
    for link in external_links:
        print(link)
