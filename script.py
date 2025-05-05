import os
import sys
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import base64

# 从环境变量获取 ChromeDriver 路径
chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
if not chromedriver_path:
    print("环境变量 CHROMEDRIVER_PATH 未设置，请检查工作流配置")
    sys.exit(1)

# 从环境变量获取 Telegram 频道 URL
channel_urls_str = os.getenv('CHANNEL_URLS')
if not channel_urls_str:
    print("环境变量 CHANNEL_URLS 未设置，请在 GitHub Secrets 中配置")
    sys.exit(1)
channel_urls = channel_urls_str.split(',')

# 设置 Chrome 无头模式选项
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# 初始化 Selenium WebDriver
service = Service(executable_path=chromedriver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# Base64 编码的搜索关键字
encoded_search_keyword = "L2FwaS92MS9jbGllbnQvc3Vic2NyaWJlP3Rva2VuPQ=="

try:
    all_urls = set()
    for channel_url in channel_urls:
        driver.get(channel_url)

        # 滚动页面以加载所有消息
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # 等待新内容加载
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:  # 如果页面高度不再变化，说明已加载所有消息
                break
            last_height = new_height

        # 解码搜索关键字
        search_keyword = base64.b64decode(encoded_search_keyword).decode()

        # 提取含有特定模式的超链接
        elements = driver.find_elements(By.CSS_SELECTOR, f'a[href*="{search_keyword}"]')
        for element in elements:
            url = element.get_attribute('href')
            if url and url.startswith('http'):  # 确保是绝对 URL
                all_urls.add(url)

finally:
    # 关闭浏览器
    driver.quit()

# 测试每个 URL 的连通性
reachable_urls = []
for url in all_urls:
    try:
        response = requests.get(url, timeout=5)  # 设置 5 秒超时
        if response.status_code == 200:
            reachable_urls.append(url)
    except requests.exceptions.RequestException:
        # 如果请求失败（超时、连接错误等），跳过该 URL
        pass

# 保存可连通的 URL 到文件
os.makedirs('data', exist_ok=True)  # 创建 data 目录（如果不存在）
with open('data/t.txt', 'w') as f:
    for url in reachable_urls:
        f.write(url + '\n')

print(f"已提取并保存 {len(reachable_urls)} 个可连通的 URL 到 data/t.txt")
