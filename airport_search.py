import requests
import re
import os
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("BOT")
# 模拟真实浏览器，防止被 Cloudflare 屏蔽
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,all;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}

# 增加更稳健的数据源：专注于“订阅转换”后端，这些后端经常包含大量活跃机场
DATA_SOURCES = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday",
    "https://raw.githubusercontent.com/freefq/free/master/README.md",
    "https://raw.githubusercontent.com/oslook/free-ssr/master/README.md"
]

FINGERPRINTS = [
    "/theme/Rocket/assets/", "/theme/Aurora/static/", "/theme/default/assets/umi.js",
    "/theme/Xoouo-Simple/assets/umi.js", "/assets/umi", "v2board", "xboard",
    "SSPanel-Uim", "layouts__index.async.js"
]

def get_domains():
    domains = set()
    exclude = r't\.me|github|google|baidu|telegram|wikipedia|apple|microsoft|cloudflare|jsdelivr'
    pattern = re.compile(r'https?://(?:(?!' + exclude + r')[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for url in DATA_SOURCES:
        try:
            res = requests.get(url, headers=HEADERS, timeout=12)
            if res.status_code == 200:
                links = pattern.findall(res.text)
                for link in links:
                    domains.add(link.strip().rstrip('/'))
        except: continue
    return domains

def check_airport(domain):
    # 探测路径列表 (V2Board 标准, XBoard 变体, SSPanel)
    api_paths = ["/api/v1/guest/config", "/api/v1/client/subscribe", "/auth/register"]
    
    try:
        # 先抓首页看指纹
        index_res = requests.get(domain, headers=HEADERS, timeout=7, verify=False)
        html = index_res.text
        hit_fp = next((fp for fp in FINGERPRINTS if fp in html), None)

        # 循环探测 API 路径
        for path in api_paths:
            test_url = f"{domain}{path}"
            res = requests.get(test_url, headers=HEADERS, timeout=7, verify=False)
            
            if res.status_code == 200:
                # 处理 V2Board/XBoard JSON 响应
                if "application/json" in res.headers.get("Content-Type", ""):
                    data = res.json().get('data', {})
                    if data:
                        title = data.get('title') or data.get('name', '未知机场')
                        give = data.get('reg_give_data', 0)
                        verify = "验证" if data.get('email_verify') == 1 else "直接注"
                        if give > 0:
                            return f"✅ 识别 | {title} | {domain} | {give}GB | {verify}"
                
                # 处理 SSPanel 注册页
                if "注册" in res.text or "Register" in res.text:
                    return f"ℹ️ 注册页 | SSPanel | {domain} | 需手动 | 页面开启"

        # 如果只有指纹命中
        if hit_fp:
            return f"🔍 指纹 | {hit_fp.split('/')[-1]} | {domain} | 需点击 | 命中特征"
            
    except: pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"=== 任务开始: {now} ===")
    raw_domains = get_domains()
    print(f"[*] 提取到 {len(raw_domains)} 个链接，开始深度多路径探测...")
    
    valid_results = []
    # 适当降低并发，防止触发 WAF 封禁
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_airport, d) for d in raw_domains]
        for future in futures:
            r = future.result()
            if r: valid_results.append(r)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (高成功率版)\n")
        f.write(f"> 更新时间: {now}\n\n")
        f.write("| 状态 | 名称 | 网址 | 流量 | 门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        if not valid_results:
            f.write("| ❌ | 暂无有效数据 | 建议添加私藏域名到 DATA_SOURCES | - | - |\n")
        else:
            valid_results.sort(reverse=True)
            for line in valid_results:
                icon, name, url, flow, door = line.split(' | ')
                f.write(f"| {icon} | {name} | {url} | {flow} | {door} |\n")
    print(f"=== 任务结束，找到 {len(valid_results)} 个有效目标 ===")

if __name__ == "__main__":
    main()
