import requests
import time
import os

# 将你的特征转化为 urlscan 的搜索语法
# page.content: 匹配页面内容
# filename: 匹配加载的资源文件名
QUERIES = [
    'page.content:"/theme/Rocket/assets/"',
    'page.content:"/theme/Aurora/static/"',
    'page.content:"v2board"',
    'page.content:"xboard"',
    'filename:"layouts__index.async.js"',
    'page.content:"Unauthenticated."'
]

def search_urlscan(query):
    print(f"正在搜索: {query}")
    # urlscan 的公开搜索 API（不需要 API Key，但有速率限制）
    search_url = f"https://urlscan.io/api/v1/search/?q={query}&size=100"
    
    try:
        response = requests.get(search_url, timeout=20)
        if response.status_code == 200:
            data = response.json()
            # 提取结果中的 URL
            return [result['page']['url'] for result in data.get('results', [])]
        elif response.status_code == 429:
            print("触发速率限制，稍后再试。")
            return []
        else:
            print(f"错误码: {response.status_code}")
            return []
    except Exception as e:
        print(f"请求异常: {e}")
        return []

if __name__ == "__main__":
    all_found = set()
    for q in QUERIES:
        urls = search_urlscan(q)
        all_found.update(urls)
        time.sleep(5) # 稍微停顿，避免被封 IP

    # 读取旧结果进行去重
    history_file = "urlscan_results.txt"
    existing = set()
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            existing = set(line.strip() for line in f)

    new_urls = all_found - existing
    
    if new_urls:
        with open(history_file, "a") as f:
            for url in new_urls:
                f.write(url + "\n")
        print(f"成功新增 {len(new_urls)} 个目标。")
    else:
        print("未发现新目标。")
