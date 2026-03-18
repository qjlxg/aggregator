import requests
import re
import os
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 更加活跃的 TG 爬取源
TG_CHANNELS = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday"
]

def get_domains_from_tg():
    domains = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 匹配域名的正则（排除掉常见的非机场域名）
    pattern = re.compile(r'https?://(?:(?!t\.me|github\.com|google\.com|baidu\.com|telegram\.org|wikipedia\.org|apple\.com|microsoft\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for channel in TG_CHANNELS:
        try:
            print(f"正在爬取频道: {channel}")
            res = requests.get(channel, headers=headers, timeout=15)
            links = pattern.findall(res.text)
            for link in links:
                domains.add(link.strip().rstrip('/'))
        except Exception as e:
            print(f"爬取 {channel} 失败: {e}")
    return domains

def check_airport(domain):
    """同时探测 V2Board 和 SSpanel"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 探测点 1: V2Board / XBoard
    try:
        res = requests.get(f"{domain}/api/v1/guest/config", headers=headers, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data and data.get('is_reg', 1) == 1:
                give = data.get('reg_give_data', 0)
                if give > 0:
                    verify = "需验证" if data.get('email_verify') == 1 else "直接注"
                    return f"✅ {data.get('title', 'V2-机场')} | {domain} | {give}GB | {verify}"
    except: pass

    # 探测点 2: SSpanel (部分站点的特征)
    try:
        res = requests.get(f"{domain}/auth/register", headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and "注册" in res.text:
            # SSpanel 很难通过 API 直接读流量，标记为手动查看
            return f"ℹ️ SS-机场 | {domain} | 需手动看 | 注册页开启"
    except: pass

    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print("开始从 Telegram 提取潜在站点...")
    potential_sites = get_domains_from_tg()
    print(f"提取到 {len(potential_sites)} 个原始链接，开始多线程扫描...")
    
    results = []
    # 使用线程池加速扫描，否则 50 个站一个个扫太慢
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_airport, site) for site in potential_sites]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (更新: {now})\n")
        f.write("| 状态 | 机场名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        if not results:
            f.write("| ❌ | 暂无有效数据 | - | - | - |\n")
        else:
            for line in results:
                icon = line.split(' ')[0]
                parts = line[2:].split(' | ')
                f.write(f"| {icon} | {' | '.join(parts)} |\n")
    print(f"任务完成，找到 {len(results)} 个有效试用机场。")

if __name__ == "__main__":
    main()
