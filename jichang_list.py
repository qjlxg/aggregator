import requests
import re
from urllib.parse import urlparse

# 定向采集的目标页面（测速博主的在线列表）
TARGET_SOURCES = [
    'https://raw.githubusercontent.com/messense/free-fq/main/README.md',
    'https://t.me/s/Duyaoss',           # 毒药的 TG 预览页
    'https://t.me/s/jichangdog',         # 机场狗
    'https://www.duyaoss.com/archives/1/', # 毒药官网文章
    'https://jichangdog.com/'            # 机场狗官网
]

def fetch_domains():
    all_domains = set()
    # 排除博主域名和干扰项
    blacklist = ['github.com', 'duyaoss.com', 'jichangdog.com', 'google.com', 't.me', 'p6p.net']
    
    # 通用域名匹配正则
    domain_pattern = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)')

    for url in TARGET_SOURCES:
        print(f"[*] 正在收割源: {url}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                # 寻找所有链接
                found = domain_pattern.findall(r.text)
                for d in found:
                    d = d.lower().replace('www.', '')
                    # 过滤逻辑：后缀检查 + 黑名单检查
                    if any(d.endswith(ext) for ext in ['.com', '.net', '.top', '.xyz', '.shop', '.cc', '.me']):
                        if not any(b in d for b in blacklist):
                            all_domains.add(d)
        except Exception as e:
            print(f"[!] 无法访问 {url}: {e}")

    return sorted(list(all_domains))

if __name__ == "__main__":
    domains = fetch_domains()
    if domains:
        with open("trial.cfg", "w", encoding="utf-8") as f:
            f.write("\n".join(domains))
        print(f"[+] 采集完成，共获取 {len(domains)} 个精品域名。")
