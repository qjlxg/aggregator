import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup

# 从环境变量中获取关键字
keyword = os.getenv("SEARCH_KEYWORD")

# 配置 Chrome headless 模式
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# 实例化 WebDriver
driver = webdriver.Chrome(options=chrome_options)

# 访问 Google 搜索页面
driver.get("https://www.google.com")

# 找到搜索框，输入关键字并提交
search_box = driver.find_element(By.NAME, "q")
search_box.send_keys(keyword)
search_box.send_keys(Keys.RETURN)

# 等待页面加载
driver.implicitly_wait(10)

# 获取页面源码并解析
soup = BeautifulSoup(driver.page_source, "html.parser")

# 提取包含关键字的链接
links = []
for a in soup.find_all("a"):
    href = a.get("href")
    if href and keyword in href:
        links.append(href)

# 关闭 WebDriver
driver.quit()

# 测试链接连通性
results = []
for link in links:
    try:
        response = requests.get(link, timeout=5)
        if response.status_code == 200:
            results.append(f"{link} - Accessible")
        else:
            results.append(f"{link} - Not Accessible (Status Code: {response.status_code})")
    except requests.exceptions.RequestException as e:
        results.append(f"{link} - Error: {str(e)}")

# 确保 data 目录存在
os.makedirs("data", exist_ok=True)

# 将结果保存到文件
with open("data/ji.txt", "w") as f:
    for result in results:
        f.write(result + "\n")
