import requests
import time
import os
import re

# 禁用不安全请求的警告（针对某些自签名证书的面板）
requests.packages.urllib3.disable_warnings()

# 1. 搜索语法优化：增加过滤，排除 urlscan 自己的结果和常见干扰域名
QUERIES = [
    'url:"*/theme/Rocket/assets/*" AND NOT domain:urlscan.io',
    'url:"*/theme/Aurora/static/*" AND NOT domain:urlscan.io',
    'url:"*/theme/default/assets/umi.js"',
    'page.content:"v2board" AND NOT domain:github.com',
    'page.content:"xboard" AND NOT domain:github.com',
    'filename:"layouts__index.async.js"'
]

# 2. 深度验证指纹（只有包含以下内容之一才算有效）
FINGERPRINTS = [
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

def verify_target(url):
    """访问目标，验证是否真实存在指纹"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        # 增加 10 秒超时
        response = requests.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
        content = response.text
        
        for fp in FINGERPRINTS:
            if fp in content:
                print(f"[+] 验证成功: {url} (匹配: {fp})")
                return True
        return False
    except Exception:
        return False

def get_urlscan_results(query):
    """从 urlscan 抓取原始数据"""
    print(f"[*] 正在检索关键词: {query}")
    api_url = f"https://urlscan.io/api/v1/search/?q={query}&size=100"
    try:
        res = requests.get(api_url, timeout=20)
        if res.status_code == 200:
            results = res.json().get('results', [])
            return [r['page']['url'] for r in results if 'page' in r]
        elif res.status_code == 429:
            print("[!] 触发速率限制，等待中...")
            time.sleep(10)
        return []
    except Exception as e:
        print(f"[!] 请求异常: {e}")
        return []

if __name__ == "__main__":
    raw_urls = set()
    for q in QUERIES:
        found = get_urlscan_results(q)
        raw_urls.update(found)
        time.sleep(2) # 礼貌间歇

    print(f"[*] 原始发现 {len(raw_urls)} 个地址，开始深度验证...")

    valid_urls = []
    for url in raw_urls:
        if verify_target(url):
            valid_urls.append(url)
    
    # 结果去重并保存
    history_file = "valid_assets.txt"
    existing = set()
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            existing = set(line.strip() for line in f)

    new_finds = [u for u in valid_urls if u not in existing]
    
    if new_finds:
        with open(history_file, "a") as f:
            for u in new_finds:
                f.write(u + "\n")
        print(f"[*] 完成！新增 {len(new_finds)} 个真实资产。")
    else:
        print("[*] 未发现新的有效资产。")
