import requests
import re
import os
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("BOT")
# 混合数据源：TG 频道预览 + 订阅转换常用后端
DATA_SOURCES = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday",
    "https://raw.githubusercontent.com/toss-p/Airport/main/Airports.md"
]

# 你提供的核心指纹关键字
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

def get_domains():
    domains = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    exclude = r't\.me|github|google|baidu|telegram|wikipedia|apple|microsoft|cloudflare|jsdelivr'
    pattern = re.compile(r'https?://(?:(?!' + exclude + r')[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for url in DATA_SOURCES:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            links = pattern.findall(res.text)
            for link in links:
                domains.add(link.strip().rstrip('/'))
        except: continue
    return domains

def check_airport(domain):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        # 1. 首页指纹匹配 (验证是否为目标面板)
        index_res = requests.get(domain, headers=headers, timeout=6, verify=False)
        html = index_res.text
        is_target = any(fp in html for fp in FINGERPRINTS)
        
        # 2. 尝试获取 V2Board/XBoard 配置
        config_res = requests.get(f"{domain}/api/v1/guest/config", headers=headers, timeout=6, verify=False)
        if config_res.status_code == 200:
            data = config_res.json().get('data', {})
            if data and data.get('is_reg', 1) == 1:
                give = data.get('reg_give_data', 0)
                if give > 0:
                    verify = "验证码" if data.get('email_verify') == 1 else "直接注"
                    return f"✅ V2/X | {data.get('title', '未知机场')} | {domain} | {give}GB | {verify}"

        # 3. 兜底策略：如果匹配到指纹但 API 没开，记录为潜在目标
        if is_target or "注册" in html or "Register" in html:
            return f"ℹ️ 匹配 | 手动确认 | {domain} | 需点击 | 命中指纹"
            
    except: pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"[{now}] 正在扫描全网指纹站点...")
    all_links = get_domains()
    print(f"提取到 {len(all_links)} 个潜在链接，开始深度指纹比对...")
    
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_airport, site) for site in all_links]
        for future in futures:
            res = future.result()
            if res: results.append(res)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场指纹情报库 (更新: {now})\n")
        f.write("| 类型 | 机场名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        if not results:
            f.write("| ❌ | 暂无有效数据 | 尝试更换数据源 | - | - |\n")
        else:
            results.sort(reverse=True)
            for line in results:
                parts = line.split(' | ')
                f.write(f"| {' | '.join(parts)} |\n")
    print(f"完成！找到 {len(results)} 个匹配站点。")

if __name__ == "__main__":
    main()
