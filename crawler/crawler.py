import requests
from bs4 import BeautifulSoup
import time
import os

# Bing 搜索 URL 模板，关键词为“机场+vpn”
BASE_URL = "https://www.bing.com/search?q=机场+vpn&first={}"

# 存储所有提取的网址，使用集合去重
all_urls = set()

# 设置请求头，模拟浏览器访问
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# 爬取前 5 页
for page in range(0, 5):
    # 计算分页参数 first（0=第1页，10=第2页，依此类推）
    first = page * 10
    url = BASE_URL.format(first)
    
    # 发送 HTTP 请求
    print(f"正在爬取页面: {url}")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"无法访问页面: {url}, 状态码: {response.status_code}")
        continue
    
    # 解析 HTML
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 提取搜索结果中的网址
    for result in soup.find_all("li", class_="b_algo"):
        link = result.find("a")
        if link and "href" in link.attrs:
            all_urls.add(link["href"])
    
    # 添加 2 秒延迟，避免请求过快被封禁
    time.sleep(2)

# 创建 data 目录（如果不存在）
os.makedirs("data", exist_ok=True)

# 保存去重后的网址到 data/ji.txt
with open("data/ji.txt", "w", encoding="utf-8") as f:
    for url in sorted(all_urls):
        f.write(url + "\n")

print("爬取完成，结果已保存到 data/ji.txt")
