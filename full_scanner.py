import requests
import re
import time
import os
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 屏蔽警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区 ---
GITHUB_TOKEN = os.getenv("BOT")
SEARCH_KEYWORDS = [
    'layouts__index.async.js',
    'v2board admin',
    'xboard docker-compose'
]

# 更加精准的黑名单，把那些刷屏的域名全部干掉
BLACKLIST = [
    'github.com', 'githubusercontent.com', 'ant.design', 'zhihu.com', 
    'npmjs.com', 'codecov.io', 'alipayobjects.com', 'jsdelivr.net', 
    'badgen.net', 'bundlephobia.com', 'google.com', 'twitter.com',
    'facebook.com', 'docker.com', 'microsoft.com', 'apple.com',
    'wikipedia.org', 'cloudflare.com', 'v2fly.org', 'trojan-gfw',
    'shields.io', 'travis-ci.org', 'reactjs.org', 'vuejs.org'
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
}

def verify_live(url):
    """验证链接是否存活"""
    # 过滤明显的非面板域名
    if any(domain in url.lower() for domain in BLACKLIST):
        return None
    
    try:
        # 只要能正常响应，就先记录下来
        r = requests.get(url, timeout=10, verify=False, allow_redirects=True, headers=HEADERS)
        if r.status_code == 200:
            print(f"[+] 发现存活站点: {url}")
            return url
    except:
        pass
    return None

def fetch_links_from_github(keyword):
    """从搜索结果中提取所有链接"""
    print(f"[*] 正在搜索 GitHub: {keyword}")
    links = set()
    url = f"https://api.github.com/search/code?q={keyword}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                # 1. 尝试从仓库描述中抓链接
                repo_api_url = item['repository']['url']
                repo_info = requests.get(repo_api_url, headers=HEADERS, timeout=10).json()
                if repo_info.get('homepage'):
                    links.add(repo_info['homepage'])
                
                # 2. 从描述中用正则扣链接
                desc = repo_info.get('description', '')
                if desc:
                    found = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', desc)
                    links.update(found)
        time.sleep(5)
    except Exception as e:
        print(f"[!] 搜索出错: {e}")
    return links

if __name__ == "__main__":
    all_potential = set()
    for kw in SEARCH_KEYWORDS:
        all_potential.update(fetch_links_from_github(kw))

    print(f"[*] 原始搜集到 {len(all_potential)} 个链接，开始存活验证...")

    live_sites = set()
    # 提高线程数到 20，加快速度
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(verify_live, all_potential)
        for r in results:
            if r: live_sites.add(r)

    # 保存结果
    with open("live_panels.txt", "w") as f:
        for site in sorted(live_sites):
            f.write(site + "\n")
            
    print(f"\n[DONE] 扫描完成。当前有效站点总数: {len(live_sites)}")
