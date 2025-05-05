import os
import sys
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 检查命令行参数，获取 Telegram 频道 URL
if len(sys.argv) < 2:
    print("请提供 Telegram 频道 URL，例如：https://t.me/somechannel")
    sys.exit(1)
channel_url = sys.argv[1]

# 设置 Chrome 无头模式选项，适应 GitHub Actions 环境
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# 初始化 Selenium WebDriver
driver = webdriver.Chrome(options=chrome_options)

try:
    # 访问 Telegram 频道页面
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

    # 提取含有特定模式的超链接
    urls = set()
    elements = driver.find_elements_by_css_selector('a[href*="/api/v1/client/subscribe?token="]')
    for element in elements:
        url = element.get_attribute('href')
        if url and url.startswith('http'):  # 确保是绝对 URL
            urls.add(url)

finally:
    # 关闭浏览器
    driver.quit()

# 测试每个 URL 的连通性
reachable_urls = []
for url in urls:
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
