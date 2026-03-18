import requests
import os
import re
from datetime import datetime
import pytz
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("BOT")
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

# 增加对核心 JS 文件的指纹匹配
QUERIES = [
    '"window.settings" "assets_path" "i18n"',
    'filename:index.html "window.settings"'
]

def extract_api_url(pages_url):
    """从 GitHub Pages 页面提取真正的后端 API 地址"""
    try:
        res = requests.get(pages_url, timeout=5, verify=False)
        # 寻找 JS 配置中的后端地址，通常在 window.settings 里
        # 或者在 umi.js 等混淆代码中
        content = res.text
        
        # 匹配常见的 API 域名格式
        # 很多机场主会直接把 API 地址写在 index.html 的 script 标签里
        match = re.search(r'host:\s*["\'](https?://[a-zA-Z0-9.-]+)["\']', content)
        if not match:
            # 另一种常见的 V2Board 变量名
            match = re.search(r'url:\s*["\'](https?://[a-zA-Z0-9.-]+)["\']', content)
        
        return match.group(1) if match else pages_url
    except:
        return pages_url

def check_airport_v2(api_base_url):
    """检测真正的后端 API"""
    api_base_url = api_base_url.strip().rstrip('/')
    # 尝试 V2Board 标准 API 路径
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
            reg = data.get('is_reg', 1)
            
            if reg == 1:
                return f"✅ {title} | {api_base_url} | {give_gb}GB | {verify}"
    except:
        pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    pages_to_check = set()
    for q in QUERIES:
        search_url = f"https://api.github.com/search/code?q={q}&sort=indexed"
        try:
            res = requests.get(search_url, headers=HEADERS, timeout=15)
            for item in res.json().get('items', []):
                owner = item['repository']['owner']['login']
                repo = item['repository']['name']
                pages_to_check.add(f"https://{owner}.github.io/{repo}/")
        except: continue

    print(f"找到 {len(pages_to_check)} 个线索，深度探测开始...")
    
    results = []
    for p in pages_to_check:
        # 第一步：找后端
        real_api = extract_api_url(p)
        # 第二步：测白嫖
        info = check_airport_v2(real_api)
        if info:
            results.append(info)
        elif real_api != p: # 如果提取到了不同的后端，再测一次
             info = check_airport_v2(p)
             if info: results.append(info)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (更新: {now})\n")
        f.write("| 机场名称 | 后端网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        if not results:
            f.write("| 正在深度爬取中，请稍后手动重试 | - | - | - |\n")
        for line in results:
            parts = line.replace('✅ ', '').split(' | ')
            f.write(f"| {' | '.join(parts)} |\n")

if __name__ == "__main__":
    main()
