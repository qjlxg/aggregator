import requests
import re
import os
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 混合数据源：TG 频道 + GitHub 订阅转换源 (这些源通常包含大量活着的机场域名)
DATA_SOURCES = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday",
    # 增加一个 GitHub 上的订阅转换配置文件作为源，这里面全是域名
    "https://raw.githubusercontent.com/toss-p/Airport/main/Airports.md"
]

def get_domains():
    domains = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 增强版正则：排除掉社交媒体、CDN、支付和大型科技公司
    exclude_list = r't\.me|github|google|baidu|telegram|wikipedia|apple|microsoft|cloudflare|jsdelivr|crashlytics|content-type'
    pattern = re.compile(r'https?://(?:(?!' + exclude_list + r')[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for url in DATA_SOURCES:
        try:
            print(f"正在从源提取数据: {url}")
            res = requests.get(url, headers=headers, timeout=15)
            links = pattern.findall(res.text)
            for link in links:
                # 过滤掉常见的非机场路径
                clean_link = link.strip().rstrip('/')
                if len(clean_link.split('.')) >= 2:
                    domains.add(clean_link)
        except Exception as e:
            print(f"读取源 {url} 失败: {e}")
    return domains

def check_airport(domain):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 策略 1: V2Board / XBoard API (最准)
    try:
        res = requests.get(f"{domain}/api/v1/guest/config", headers=headers, timeout=6, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data and data.get('is_reg', 1) == 1:
                give = data.get('reg_give_data', 0)
                if give > 0:
                    verify = "验证码" if data.get('email_verify') == 1 else "直接注"
                    return f"✅ V2 | {data.get('title', '未知机场')} | {domain} | {give}GB | {verify}"
    except: pass

    # 策略 2: 常见注册路径探测 (SSpanel/Panda)
    try:
        # 很多站点的 API 隐藏了，但注册页是开着的
        res = requests.get(f"{domain}/auth/register", headers=headers, timeout=6, verify=False)
        if res.status_code == 200 and ("注册" in res.text or "Register" in res.text):
            return f"ℹ️ SS | 手动查看 | {domain} | 需点击 | 注册页开"
    except: pass

    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print("开始提取潜在站点...")
    all_links = get_domains()
    print(f"总计提取到 {len(all_links)} 个链接，开始并发探测...")
    
    results = []
    # 增加并发数到 15，提高效率
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(check_airport, site) for site in all_links]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (更新: {now})\n")
        f.write("> 提示：✅ 格式表示自动识别成功；ℹ️ 格式表示需手动打开注册页确认。\n\n")
        f.write("| 类型 | 机场名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        
        if not results:
            f.write("| ❌ | 暂无有效数据 | 请检查 DATA_SOURCES 是否失效 | - | - |\n")
        else:
            # 简单排序：V2Board 优先
            results.sort(reverse=True)
            for line in results:
                parts = line.split(' | ')
                f.write(f"| {' | '.join(parts)} |\n")
    
    print(f"探测结束，找到 {len(results)} 个有效目标。")

if __name__ == "__main__":
    main()
