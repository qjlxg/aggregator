import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import os

# 设置Selenium
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # 无头模式
options.add_argument("--no-sandbox")  # CI环境需要的参数
options.add_argument("--disable-dev-shm-usage")  # 解决资源限制问题
driver = webdriver.Chrome(options=options)

# 目标URL
base_url = "https://t.me/s/V2ray_Click"

# 存储所有链接
all_links = set()

# 获取页面内容并提取链接
def fetch_links():
    driver.get(base_url)
    time.sleep(3)  # 等待页面初次加载

    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # 等待新内容加载
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:  # 如果高度不再变化，说明加载完成
            break
        last_height = new_height

    html_content = driver.page_source
    soup = BeautifulSoup(html_content, 'html.parser')
    for a_tag in soup.find_all('a', href=True):
        all_links.add(a_tag['href'])

# 主逻辑
fetch_links()

# 关闭浏览器
driver.quit()

# 确保data目录存在
os.makedirs('data', exist_ok=True)

# 将去重后的链接保存到文件
with open('data/ji.txt', 'w', encoding='utf-8') as file:
    for link in sorted(all_links):
        file.write(link + '\n')

print("所有唯一链接已保存到 'data/ji.txt' 中。")
