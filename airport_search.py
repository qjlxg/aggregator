import requests
import re
import os
from datetime import datetime
import pytz
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TG 频道列表（这些是公开预览版，无需登录即可爬取）
TG_CHANNELS = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/vpneveryday",
    "https://t.me/s/mianfeiairport"
]

def get_domains_from_tg():
    """从 TG 频道网页预览中提取所有域名"""
    domains = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for channel in TG_CHANNELS:
        try:
            print(f"正在爬取频道: {channel}")
            res = requests.get(channel, headers=headers, timeout=15)
            # 提取所有 http/https 链接
            links = re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res.text)
            for link in links:
                # 过滤掉干扰链接
                if "t.me" in link or "github" in link or "google" in link:
                    continue
                domains.add(link.strip().rstrip('/'))
        except Exception as e:
            print(f"爬取 {channel} 失败: {e}")
    return domains

def check_airport_v2(api_base_url):
    """检测 API 是否送流量"""
    check_url = f"{api_base_url}/api/v1/guest/config"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(check_url, headers=headers, timeout=8, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if not data: return None
            
            title = data.get('title', '未知机场')
            give_gb = data.get('reg_give_data', 0)
            verify = "验证" if data.get('email_verify') == 1 else "直接注"
            
            # 只要送流量且开放注册，就记录
            if data.get('is_reg', 1) == 1 and give_gb > 0:
                return f"✅ {title} | {api_base_url} | {give_gb}GB | {verify}"
    except:
        pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print("开始从 Telegram 提取潜在站点...")
    potential_sites = get_domains_from_tg()
    print(f"提取到 {len(potential_sites)} 个原始链接，开始筛选有效机场...")
    
    results = []
    for site in potential_sites:
        info = check_airport_v2(site)
        if info:
            results.append(info)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (TG源更新: {now})\n")
        f.write("| 机场名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        if not results:
            f.write("| 暂无有效数据，可能频道暂无更新 | - | - | - |\n")
        else:
            # 按流量大小排序
            results.sort(key=lambda x: float(re.findall(r'(\d+)', x.split('|')[2])[0]), reverse=True)
            for line in results:
                parts = line.replace('✅ ', '').split(' | ')
                f.write(f"| {' | '.join(parts)} |\n")
    print(f"任务完成，共找到 {len(results)} 个有效试用机场。")

if __name__ == "__main__":
    main()
