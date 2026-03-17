import requests
import re
from urllib.parse import urlparse

# 依然使用这些优质源
TARGET_SOURCES = [
    'https://raw.githubusercontent.com/messense/free-fq/main/README.md',
    'https://t.me/s/Duyaoss',
    'https://t.me/s/jichangdog',
    'https://www.duyaoss.com/archives/1/',
    'https://jichangdog.com/'
]

def fetch_clean_domains():
    all_domains = set()
    
    # 1. 严格黑名单：这些词出现在域名里直接滚蛋
    trash_keywords = [
        'google', 'baidu', 'weixin', 'weibo', 'x.com', 'twitter', 'github', 
        'blogspot', 'gravatar', 'wccftech', 'v2ray', 'clash', 'githubusercontent',
        'cloudflare', 'amazonaws', 'jsdmirror', 'cdn', 'static', 'fonts', 'api'
    ]
    
    # 2. 机场偏好后缀
    valid_suffixes = ('.xyz', '.top', '.shop', '.cc', '.net', '.org', '.icu', '.ink', '.cfd', '.link')

    domain_pattern = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)')

    for url in TARGET_SOURCES:
        try:
            print(f"[*] 扫描源: {url}")
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                found = domain_pattern.findall(r.text)
                for d in found:
                    d = d.lower().replace('www.', '')
                    
                    # 过滤逻辑 A: 长度检查（太短的可能是博主缩写）
                    if len(d) < 5: continue
                    
                    # 过滤逻辑 B: 后缀检查
                    if not d.endswith(valid_suffixes): continue
                    
                    # 过滤逻辑 C: 关键词检查
                    if any(trash in d for trash in trash_keywords): continue
                    
                    all_domains.add(d)
        except: continue

    return sorted(list(all_domains))

if __name__ == "__main__":
    domains = fetch_clean_domains()
    with open("trial.cfg", "w", encoding="utf-8") as f:
        f.write("\n".join(domains))
    print(f"[+] 清洗完毕！共保留 {len(domains)} 个潜在机场入口。")
