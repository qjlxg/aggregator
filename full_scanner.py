import requests
import re
import time
import os
import base64
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 1. 屏蔽 SSL 警告，保持日志干净
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区 ---
GITHUB_TOKEN = os.getenv("BOT")
# 你提供的核心特征词，用于二次验证
TARGET_BODY_FEATURES = [
    "/theme/Rocket/assets/",
    "/theme/Aurora/static/",
    "/theme/default/assets/umi.js",
    "/theme/Xoouo-Simple/assets/umi.js",
    "/assets/umi",
    "v2board",
    "xboard",
    "SSPanel-Uim",
    '{"message":"Unauthenticated."}',
    "layouts__index.async.js"
]

# 用于 GitHub 搜索的关键词（尽量选取唯一性强的文件名）
SEARCH_KEYWORDS = [
    'layouts__index.async.js',
    '"/theme/Rocket/assets/"',
    '"xboard" "docker-compose"',
    '"v2board" "admin"'
]

# 排除已知的噪音域名
BLACKLIST = [
    'github.com', 'githubusercontent.com', 'ant.design', 'zhihu.com', 
    'npmjs.com', 'codecov.io', 'alipayobjects.com', 'jsdelivr.net', 
    'badgen.net', 'bundlephobia.com', 'google.com', 'twitter.com',
    'facebook.com', 'docker.com', 'microsoft.com', 'apple.com',
    'wikipedia.org', 'cloudflare.com', 'v2fly.org', 'trojan-gfw'
]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
}

def verify_live_panel(url):
    """验证 URL 是否存活且包含你指定的特征"""
    try:
        # 模拟真实浏览器
        r = requests.get(url, timeout=12, verify=False, allow_redirects=True, headers=HEADERS)
        if r.status_code == 200:
            html_content = r.text
            # 只要 body 中包含你给出的任何一个特征，即视为命中
            for feature in TARGET_BODY_FEATURES:
                if feature in html_content:
                    print(f"[+] 发现存活目标: {url} (匹配特征: {feature})")
                    return url
    except:
        pass
    return None

def get_urls_from_repo(repo_fullname):
    """深度钻取仓库内的 URL 链接"""
    found_urls = []
    files_to_check = ['README.md', 'docker-compose.yml', '.env.example']
    
    for file in files_to_check:
        api_url = f"https://api.github.com/repos/{repo_fullname}/contents/{file}"
        try:
            res = requests.get(api_url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8', errors='ignore')
                # 提取 http/https 链接
                raw_links = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', content)
                for l in raw_links:
                    l = l.rstrip('.')
                    if not any(b in l.lower() for b in BLACKLIST):
                        found_urls.append(l)
        except:
            continue
    return list(set(found_urls))

if __name__ == "__main__":
    live_sites = set()
    all_potential_links = set()

    # 1. 从 GitHub 搜索仓库
    for kw in SEARCH_KEYWORDS:
        search_url = f"https://api.github.com/search/code?q={kw}"
        try:
            res = requests.get(search_url, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                items = res.json().get('items', [])
                for item in items:
                    repo_name = item['repository']['full_name']
                    all_potential_links.update(get_urls_from_repo(repo_name))
            time.sleep(5) # 遵守 GitHub 速率限制
        except Exception as e:
            print(f"[!] 搜索出错: {e}")

    # 2. 多线程验证存活及特征 (提高效率)
    print(f"[*] 开始验证 {len(all_potential_links)} 个潜在链接...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(verify_live_panel, all_potential_links)
        for r in results:
            if r:
                live_sites.add(r)

    # 3. 结果保存与去重
    history_file = "live_panels.txt"
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            live_sites.update(line.strip() for line in f)

    with open(history_file, "w") as f:
        for site in sorted(live_sites):
            f.write(site + "\n")
            
    print(f"\n[DONE] 扫描完成。当前有效面板总数: {len(live_sites)}")
