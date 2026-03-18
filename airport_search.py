import requests
import base64
import os
import time
from datetime import datetime
import pytz

# 配置 GitHub Token (从环境变量获取)
TOKEN = os.getenv("BOT")
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# 搜索关键词：锁定 V2Board/XBoard 特征
QUERY = '"window.settings" "assets_path" "theme/default/assets" "i18n"'

def search_github():
    print(f"[{datetime.now()}] 开始搜索 GitHub 仓库...")
    url = f"https://api.github.com/search/code?q={QUERY}&sort=indexed&order=desc"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"搜索失败: {res.status_code} - {res.text}")
            return []
        
        items = res.json().get('items', [])
        found_sites = []
        
        for item in items:
            owner = item['repository']['owner']['login']
            repo = item['repository']['name']
            # 自动推导 GitHub Pages 潜在地址
            pages_url = f"https://{owner}.github.io/{repo}/"
            found_sites.append(f"{pages_url} (Repo: {owner}/{repo})")
            
        return list(set(found_sites)) # 去重
    except Exception as e:
        print(f"发生异常: {e}")
        return []

def main():
    sites = search_github()
    
    # 设置上海时区
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"--- 最后更新时间 (上海): {now} ---\n")
        if not sites:
            f.write("本次未搜索到新结果。\n")
        for site in sites:
            f.write(f"{site}\n")
    
    print(f"结果已写入 results.txt，共找到 {len(sites)} 个潜在目标。")

if __name__ == "__main__":
    main()
