import requests
import re
import time
import os

# 从你设置的 Secret 中读取 Token
GITHUB_TOKEN = os.getenv("BOT") 
KEYWORDS = [
    'layouts__index.async.js',
    '"xboard" "docker-compose"',
    '"v2board" "admin"'
]

def search_github(keyword):
    print(f"[*] 正在检索关键词: {keyword}")
    # 使用 API 搜索代码
    url = f"https://api.github.com/search/code?q={keyword}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            items = res.json().get('items', [])
            return items
        else:
            print(f"[!] 出错: {res.status_code}")
            return []
    except Exception as e:
        print(f"[!] 请求异常: {e}")
        return []

def extract_urls(text):
    # 匹配 http/https 链接的正则表达式
    regex = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    links = re.findall(regex, text)
    # 过滤掉 github 相关的干扰链接
    return [l for l in links if "github" not in l and "schema" not in l]

if __name__ == "__main__":
    found_sites = set()
    
    for kw in KEYWORDS:
        results = search_github(kw)
        for item in results:
            # 1. 尝试从文件路径或仓库描述中找
            repo_name = item['repository']['full_name']
            desc = item['repository'].get('description', '')
            if desc:
                found_sites.update(extract_urls(desc))
            
            # 2. 这里的搜索结果其实包含文件内容，但为了省流量，我们可以记录仓库地址
            # 后续你可以手动查看这些搜出来的仓库
            found_sites.add(f"Repo: https://github.com/{repo_name}")
            
        time.sleep(10) # 遵守 API 频率限制

    # 存入结果
    with open("discovered_sites.txt", "a") as f:
        for site in found_sites:
            f.write(site + "\n")
            
    print(f"[*] 扫描结束，结果已更新至 discovered_sites.txt")
