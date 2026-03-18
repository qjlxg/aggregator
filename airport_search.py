import requests
import re
import os
import time
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("BOT")
# 模拟真实浏览器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}

# 数据源：TG 频道 + 稳定的 GitHub 镜像
DATA_SOURCES = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday",
    "https://raw.githubusercontent.com/oslook/free-ssr/master/README.md",
    "https://raw.githubusercontent.com/v2ray-free/free-v2ray-nodes/master/README.md"
]

# 核心指纹关键字
FINGERPRINTS = [
    "window.settings", "/theme/default/assets/umi.js", "v2board", "xboard",
    "SSPanel-Uim", "Rocket/assets", "Aurora/static", "Unauthenticated"
]

def get_domains():
    """多策略提取域名并清洗"""
    domains = set()
    exclude = r't\.me|github|google|baidu|telegram|wikipedia|apple|microsoft|cloudflare|jsdelivr|linktr\.ee'
    pattern = re.compile(r'https?://(?:(?!' + exclude + r')[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for url in DATA_SOURCES:
        try:
            print(f"[*] 正在抓取源: {url}")
            res = requests.get(url, headers=HEADERS, timeout=12)
            if res.status_code == 200:
                links = pattern.findall(res.text)
                for link in links:
                    # 仅保留协议+域名部分
                    parts = link.split('/')
                    if len(parts) >= 3:
                        domains.add(f"{parts[0]}//{parts[2]}")
        except:
            continue
    return domains

def check_airport(domain):
    """深度探测：指纹 + API + 注册页"""
    try:
        # 1. 首页指纹初筛
        try:
            index = requests.get(domain, headers=HEADERS, timeout=10, verify=False)
            html = index.text
            is_target = any(fp in html for fp in FINGERPRINTS)
        except:
            return None

        # 2. 探测 V2Board/XBoard (核心白嫖点)
        api_urls = [f"{domain}/api/v1/guest/config", f"{domain}/api/v1/client/subscribe"]
        for a_url in api_urls:
            try:
                res = requests.get(a_url, headers=HEADERS, timeout=10, verify=False)
                if res.status_code == 200 and "application/json" in res.headers.get("Content-Type", ""):
                    data = res.json().get('data', {})
                    if data and data.get('is_reg', 1) == 1:
                        title = data.get('title') or "未命名机场"
                        give = data.get('reg_give_data', 0)
                        verify = "验证" if data.get('email_verify') == 1 else "直接注"
                        if give > 0:
                            return f"✅ V2/X | {title} | {domain} | {give}GB | {verify}"
            except:
                pass # 这里不能写 continue，因为已不在 loop 中

        # 3. 探测 SSPanel/注册页面
        try:
            reg_res = requests.get(f"{domain}/auth/register", headers=HEADERS, timeout=10, verify=False)
            if reg_res.status_code == 200 and ("注册" in reg_res.text or "Register" in reg_res.text):
                return f"ℹ️ 注册页 | SSPanel | {domain} | 需点击 | 页面存活"
        except:
            pass

        # 4. 指纹命中兜底
        if is_target:
            return f"🔍 指纹 | 匹配特征 | {domain} | 未知 | 疑似机场"
            
    except:
        pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"=== 测绘扫描开始: {now} ===")
    raw_domains = get_domains()
    print(f"[*] 原始链接池大小: {len(raw_domains)}")
    
    results = []
    # 使用线程池并发探测
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(check_airport, d) for d in raw_domains]
        for future in futures:
            r = future.result()
            if r: 
                results.append(r)
                print(f"[+] 发现目标: {r}")

    # 写入文件
    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (修复版)\n")
        f.write(f"> 更新时间: {now} (上海)\n\n")
        f.write("| 状态 | 类型 | 网址 | 流量 | 门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        if not results:
            f.write("| ❌ | 暂无有效数据 | 可能受 CF 防护影响，请手动检查源 | - | - |\n")
        else:
            results.sort(reverse=True)
            for line in results:
                # 兼容旧逻辑的分割显示
                parts = line.split(' | ')
                f.write(f"| {' | '.join(parts)} |\n")
    
    print(f"=== 扫描结束，共获 {len(results)} 个有效目标 ===")

if __name__ == "__main__":
    main()
