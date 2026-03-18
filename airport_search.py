import requests
import re
import os
from datetime import datetime
import pytz
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 禁用 SSL 警告（机场证书经常过期）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 环境变量获取 Token
TOKEN = os.getenv("BOT")
HEADERS = {
    "Authorization": f"token {TOKEN}" if TOKEN else "",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
}

# 数据源列表（包含目前 2026 年活跃的 TG 频道和 GitHub 仓库）
DATA_SOURCES = [
    "https://t.me/s/v2ray_free",
    "https://t.me/s/Airport_Free",
    "https://t.me/s/mianfeiairport",
    "https://t.me/s/vpneveryday",
    # 备用 GitHub 源 (Raw 链接)
    "https://raw.githubusercontent.com/Pawpiee/free-checker/master/use.md",
    "https://raw.githubusercontent.com/vpei/free-node/master/README.md",
    "https://raw.githubusercontent.com/freefq/free/master/README.md"
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
    """从多个源提取域名并去重"""
    domains = set()
    # 排除列表，防止抓到无关大站
    exclude_regex = r't\.me|github|google|baidu|telegram|wikipedia|apple|microsoft|cloudflare|jsdelivr|crashlytics|content-type'
    domain_pattern = re.compile(r'https?://(?:(?!' + exclude_regex + r')[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')

    for url in DATA_SOURCES:
        try:
            print(f"[*] 正在读取源: {url}")
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                links = domain_pattern.findall(res.text)
                for link in links:
                    domains.add(link.strip().rstrip('/'))
            else:
                print(f"[!] 源失效 (HTTP {res.status_code}): {url}")
        except Exception as e:
            print(f"[!] 无法访问源 {url}: {e}")
    return domains

def check_airport(domain):
    """深度探测指纹与白嫖信息"""
    try:
        # 1. 探测 V2Board/XBoard 宾客配置 API
        api_url = f"{domain}/api/v1/guest/config"
        res = requests.get(api_url, headers=HEADERS, timeout=6, verify=False)
        
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data and data.get('is_reg', 1) == 1:
                title = data.get('title', '未知机场')
                give_gb = data.get('reg_give_data', 0)
                verify = "需验证" if data.get('email_verify') == 1 else "直接注"
                if give_gb > 0:
                    return f"✅ 识别 | {title} | {domain} | {give_gb}GB | {verify}"

        # 2. 如果 API 不通，则请求首页匹配指纹
        index_res = requests.get(domain, headers=HEADERS, timeout=6, verify=False)
        html = index_res.text
        hit_fp = next((fp for fp in FINGERPRINTS if fp in html), None)
        
        if hit_fp:
            # 标记为匹配到指纹但 API 可能被隐藏的站点
            return f"ℹ️ 指纹 | 匹配 {hit_fp.split('/')[2] if '/' in hit_fp else '主题'} | {domain} | 需点击 | 注册页开"
            
    except:
        pass
    return None

def main():
    # 设置上海时区
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"=== 任务开始: {now} ===")
    raw_domains = get_domains()
    print(f"[*] 共提取到 {len(raw_domains)} 个潜在域名，开始并发指纹比对...")
    
    valid_results = []
    # 使用 20 线程并发探测
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_airport, d) for d in raw_domains]
        for future in futures:
            result = future.result()
            if result:
                valid_results.append(result)

    # 写入 Markdown 结果文件
    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (指纹检索版)\n")
        f.write(f"> 最后更新时间: {now} (上海)\n\n")
        f.write("| 状态 | 类型/名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        
        if not valid_results:
            f.write("| ❌ | 暂无有效数据 | 请尝试手动更新 DATA_SOURCES | - | - |\n")
        else:
            # 排序：自动识别成功的排在前面
            valid_results.sort(reverse=True)
            for line in valid_results:
                icon = line.split(' ')[0]
                parts = line[2:].split(' | ')
                f.write(f"| {icon} | {' | '.join(parts)} |\n")
    
    print(f"=== 任务完成，找到 {len(valid_results)} 个有效目标 ===")

if __name__ == "__main__":
    main()
