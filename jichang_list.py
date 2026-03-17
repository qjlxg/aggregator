import requests
import re
import concurrent.futures
from urllib.parse import urlparse

# 1. 更加精准的源（专注 Xboard/V2Board 分享）
TARGET_SOURCES = [
    'https://t.me/s/v2cross',
    'https://t.me/s/star_gleam',
    'https://t.me/s/jichang_list',
    'https://raw.githubusercontent.com/messense/free-fq/main/README.md'
]

# 2. 只有包含这些关键字的页面才算是我们要找的“机场”
FINGERPRINTS = [
    '/theme/v2board/assets/umi.js',
    '/theme/Xboard/assets/umi.js',
    'v2board-config',
    'window.v2board'
]

def is_real_airport(domain):
    """验证域名是否真的是 V2Board/Xboard 机场"""
    protocols = ['https://', 'http://']
    for proto in protocols:
        try:
            url = f"{proto}{domain}"
            # 只读取前 50KB，节省流量和时间
            r = requests.get(url, timeout=10, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if r.status_code == 200:
                content = r.text
                if any(fp in content for fp in FINGERPRINTS):
                    print(f"[√] 发现有效机场: {domain}")
                    return domain
        except:
            continue
    return None

def fetch_and_verify():
    raw_domains = set()
    trash_keywords = ['telegram', 'google', 'w3.org', 'schema', 'typecho', 'f-droid', 'github', 'wikipedia', 'twitter']
    valid_suffixes = ('.xyz', '.top', '.shop', '.cc', '.net', '.org', '.icu', '.ink', '.cfd', '.link')
    
    # 提取原始数据
    domain_pattern = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)')

    for url in TARGET_SOURCES:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                found = domain_pattern.findall(r.text)
                for d in found:
                    d = d.lower().replace('www.', '')
                    if d.endswith(valid_suffixes) and not any(tk in d for tk in trash_keywords):
                        raw_domains.add(d)
        except: continue

    print(f"[*] 原始抓取到 {len(raw_domains)} 个候选域名，开始进行活体特征扫描...")

    # 使用线程池加速验证
    final_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(is_real_airport, raw_domains))
        final_list = [r for r in results if r]

    return sorted(final_list)

if __name__ == "__main__":
    verified_domains = fetch_and_verify()
    with open("trial.cfg", "w", encoding="utf-8") as f:
        f.write("\n".join(verified_domains))
    print(f"\n[+] 最终识别出 {len(verified_domains)} 个活跃机场官网。")
