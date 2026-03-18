import requests
import re
import time
import os
import base64
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区 ---
GITHUB_TOKEN = os.getenv("BOT")
# 搜索更直接的“泄露点”：配置文件
SEARCH_KEYWORDS = [
    'extension:yml "V2BOARD_URL"',
    'extension:yaml "XBOARD_URL"',
    'filename:docker-compose.yml "8080:80"',
    'filename:.env "DB_PASSWORD" "v2board"',
    '"/theme/Rocket/assets/" extension:php'
]

# 严格过滤掉已知的干扰大厂域名
BLACKLIST = [
    'github.com', 'vercel.app', 'github.io', 'ant.design', 'npmjs.com', 
    'google.com', 'apple.com', 'microsoft.com', 'docker.com', 'baidu.com',
    'zhihu.com', 'codecov.io', 'jsdelivr.net', 'facebook.com', 'twitter.com'
]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
}

def verify_and_check_body(url):
    """访问 URL 并检查你要求的 Body 特征"""
    if any(b in url.lower() for b in BLACKLIST): return None
    try:
        r = requests.get(url, timeout=10, verify=False, allow_redirects=True)
        if r.status_code == 200:
            html = r.text
            # 匹配你提供的任意一个特征
            features = [
                "/theme/Rocket/assets/", "/theme/Aurora/static/", "v2board", 
                "xboard", "SSPanel-Uim", "layouts__index.async.js"
            ]
            if any(f in html for f in features):
                print(f"[!] 命中特征站: {url}")
                return url
    except:
        pass
    return None

def get_config_links(repo_fullname):
    """深入仓库文件搜索 URL"""
    links = []
    # 尝试读取配置文件
    for file_path in ['docker-compose.yml', '.env', 'config/v2board.php', '.env.example']:
        api_url = f"https://api.github.com/repos/{repo_fullname}/contents/{file_path}"
        try:
            res = requests.get(api_url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8', errors='ignore')
                # 寻找 http 链接
                found = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', content)
                links.extend(found)
        except:
            continue
    return links

if __name__ == "__main__":
    potential_pool = set()
    
    for kw in SEARCH_KEYWORDS:
        print(f"[*] 正在挖掘 GitHub 配置文件: {kw}")
        url = f"https://api.github.com/search/code?q={kw}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                items = res.json().get('items', [])
                for item in items:
                    repo_name = item['repository']['full_name']
                    # 从配置文件中抠链接
                    potential_pool.update(get_config_links(repo_name))
            time.sleep(10) # 严格遵守速率限制
        except Exception as e:
            print(f"[!] 报错: {e}")

    print(f"[*] 挖掘到 {len(potential_pool)} 个潜在地址，开始 Body 特征核验...")

    live_panels = set()
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = executor.map(verify_and_check_body, potential_pool)
        for r in results:
            if r: live_panels.add(r)

    with open("live_panels.txt", "w") as f:
        for site in sorted(live_panels):
            f.write(site + "\n")
            
    print(f"\n[DONE] 扫描结束，共捕获 {len(live_panels)} 个特征匹配站。")
