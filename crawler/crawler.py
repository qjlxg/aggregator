import requests
from bs4 import BeautifulSoup
import time
import os

# Bing 搜索 URL 模板
BASE_URL = "https://www.bing.com/search?q=机场+vpn&first={}"

# 存储所有提取的网址，使用集合去重
all_urls = set()

# 设置请求头，模拟浏览器访问
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def get_final_url(url):
    """获取重定向后的最终 URL"""
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=5)
        return response.url
    except requests.RequestException:
        return url

# 爬取前 5 页
for page in range(0, 5):
    first = page * 10
    url = BASE_URL.format(first)
    
    print(f"正在爬取页面: {url}")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"无法访问页面: {url}, 状态码: {response.status_code}")
        continue
    
    # 解析 HTML
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 提取搜索结果中的真实网址
    for result in soup.find_all("li", class_="b_algo"):
        link = result.find("a")
        if link and "href" in link.attrs:
            extracted_url = link["href"]
            # 如果是 Bing 重定向链接，获取最终 URL
            if extracted_url.startswith("https://www.bing.com/ck/"):
                final_url = get_final_url(extracted_url)
            else:
                final_url = extracted_url
            all_urls.add(final_url)
            print(f"提取到网址: {final_url}")
    
    time.sleep(2)  # 避免请求过快被封禁

# 创建 data 目录并保存结果
os.makedirs("data", exist_ok=True)
with open("data/ji.txt", "w", encoding="utf-8") as f:
    for url in sorted(all_urls):
        f.write(url + "\n")

print("爬取完成，结果已保存到 data/ji.txt")
