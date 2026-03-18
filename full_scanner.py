import requests
import re
import time
import os
import base64

# --- 配置区 ---
GITHUB_TOKEN = os.getenv("BOT")
KEYWORDS = [
    'layouts__index.async.js',
    '"xboard" "docker-compose"',
    '"v2board" "admin"'
]
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
}

def search_repos(keyword):
    """第一步：搜索包含关键词的仓库"""
    print(f"[*] 正在 GitHub 搜索: {keyword}")
    url = f"https://api.github.com/search/code?q={keyword}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            return res.json().get('items', [])
        return []
    except:
        return []

def extract_urls_from_text(text):
    """从文本中提取非 GitHub 的 URL"""
    regex = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    links = re.findall(regex, text)
    # 过滤掉常见的无关链接
    exclude = ['github.com', 'githubusercontent.com', 'schema.org', 'wikipedia.org', 'docker.com', 'baidu.com']
    return [l.rstrip('.') for l in links if not any(ex in l for ex in exclude)]

def get_repo_secrets(repo_fullname):
    """第二步：深度探测仓库内容（README 和 配置文件）"""
    urls = []
    # 检查 README 和一些可能的配置文件
    files_to_check = ['README.md', 'docker-compose.yml', '.env.example', 'config.php']
    
    for file in files_to_check:
        file_url = f"https://api.github.com/repos/{repo_fullname}/contents/{file}"
        try:
            res = requests.get(file_url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8', errors='ignore')
                urls.extend(extract_urls_from_text(content))
        except:
            continue
    return list(set(urls))

def is_live_panel(url):
    """第三步：存活验证"""
    try:
        # 针对面板通常重定向或需要较长时间响应，设置 10s 超时
        r = requests.get(url, timeout=10, verify=False, allow_redirects=True)
        if r.status_code == 200:
            # 进一步验证是否包含面板特征
            features = ['v2board', 'xboard', 'umi.js', 'auth/login']
            if any(f in r.text.lower() for f in features):
                return True
    except:
        pass
    return False

if __name__ == "__main__":
    final_live_sites = set()
    processed_repos = set()

    for kw in KEYWORDS:
        items = search_repos(kw)
        for item in items:
            repo_name = item['repository']['full_name']
            if repo_name in processed_repos: continue
            
            # 提取潜在链接
            potential_links = get_repo_secrets(repo_name)
            
            # 验证存活
            for link in potential_links:
                print(f"[*] 验证链接: {link}")
                if is_live_panel(link):
                    print(f"[+] 发现存活面板: {link}")
                    final_live_sites.add(link)
            
            processed_repos.add(repo_name)
            time.sleep(2) # 避开频率限制

    # 写入结果
    with open("live_panels.txt", "w") as f:
        for site in sorted(final_live_sites):
            f.write(site + "\n")
            
    print(f"\n[OK] 闭环运行结束。共发现 {len(final_live_sites)} 个存活面板。")
