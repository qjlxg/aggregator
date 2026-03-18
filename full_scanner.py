import requests
import re
import time
import os
import base64
import urllib3

# 1. 屏蔽烦人的 SSL 警告日志
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区 ---
GITHUB_TOKEN = os.getenv("BOT")
KEYWORDS = [
    'layouts__index.async.js',
    '"xboard" "docker-compose"',
    '"v2board" "admin"'
]

# 严苛的黑名单：过滤掉文档、图标、统计插件等干扰项
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

def search_repos(keyword):
    """搜索包含关键词的仓库代码"""
    print(f"[*] 正在搜索 GitHub 代码: {keyword}")
    url = f"https://api.github.com/search/code?q={keyword}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            return res.json().get('items', [])
        return []
    except:
        return []

def extract_urls(text):
    """从文本中提取 URL 并进行初步过滤"""
    regex = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    links = re.findall(regex, text)
    clean_links = []
    for l in links:
        l = l.rstrip('.')
        # 排除黑名单中的域名
        if not any(b in l.lower() for b in BLACKLIST):
            clean_links.append(l)
    return list(set(clean_links))

def get_repo_contents(repo_fullname):
    """探测仓库内的关键文件"""
    urls = []
    # 扫描 README 和常见的配置文件
    for file in ['README.md', 'docker-compose.yml', '.env.example']:
        file_url = f"https://api.github.com/repos/{repo_fullname}/contents/{file}"
        try:
            res = requests.get(file_url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8', errors='ignore')
                urls.extend(extract_urls(content))
        except:
            continue
    return list(set(urls))

def verify_live_panel(url):
    """二次验证：确保 URL 存活且具有面板特征"""
    try:
        # 模拟真实浏览器请求，避免被简单的 WAF 拦截
        r = requests.get(url, timeout=10, verify=False, allow_redirects=True, headers=HEADERS)
        if r.status_code == 200:
            html = r.text.lower()
            # 只有包含这些特征词的才会被记录
            features = ['v2board', 'xboard', 'sspanel', 'umi.js', 'auth/login', 'v2b']
            if any(f in html for f in features):
                print(f"[+] 发现目标: {url}")
                return True
    except:
        pass
    return False

if __name__ == "__main__":
    live_sites = set()
    processed_repos = set()

    # 读取旧数据实现增量去重
    if os.path.exists("live_panels.txt"):
        with open("live_panels.txt", "r") as f:
            live_sites = set(line.strip() for line in f)

    for kw in KEYWORDS:
        items = search_repos(kw)
        for item in items:
            repo_name = item['repository']['full_name']
            if repo_name in processed_repos: continue
            
            # 深入仓库抓取链接
            potential_links = get_repo_contents(repo_name)
            
            # 验证每一个链接
            for link in potential_links:
                if link not in live_sites and verify_live_panel(link):
                    live_sites.add(link)
            
            processed_repos.add(repo_name)
            time.sleep(5) # 遵守 API 速率限制

    # 结果保存
    with open("live_panels.txt", "w") as f:
        for site in sorted(live_sites):
            f.write(site + "\n")
            
    print(f"\n[DONE] 扫描完成。当前共搜集到 {len(live_sites)} 个存活面板。")
