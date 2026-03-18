import requests
import os
from datetime import datetime
import pytz
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = os.getenv("BOT")
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

# 扩展搜索词列表，循环搜索以增加命中率
QUERIES = [
    '"window.settings" "assets_path" "i18n"',
    '"/theme/default/assets/umi.js"',
    'title: "V2Board" "注册"',
    '"reg_give_data"'
]

def check_site_status(url):
    """核心白嫖检测逻辑"""
    clean_url = url.split(' ')[0].rstrip('/')
    api_url = f"{clean_url}/api/v1/guest/config"
    try:
        res = requests.get(api_url, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            title = data.get('title', '未知机场')
            give_gb = data.get('reg_give_data', 0)
            need_verify = "需要验证" if data.get('email_verify') == 1 else "直接注册"
            is_reg = "开放" if data.get('is_reg') == 1 else "关闭"
            
            if data.get('is_reg') == 1:
                return f"✅ {title} | {clean_url} | 送{give_gb}GB | {need_verify}"
    except:
        pass
    return None

def main():
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    all_found_pages = set()
    
    # 遍历多个关键词扩大搜索范围
    for q in QUERIES:
        search_url = f"https://api.github.com/search/code?q={q}&sort=indexed"
        try:
            res = requests.get(search_url, headers=HEADERS, timeout=15)
            items = res.json().get('items', [])
            for item in items:
                owner = item['repository']['owner']['login']
                repo = item['repository']['name']
                all_found_pages.add(f"https://{owner}.github.io/{repo}/")
        except:
            continue

    print(f"找到 {len(all_found_pages)} 个潜在域名，开始扫描试用信息...")
    
    final_results = []
    for site in all_found_pages:
        info = check_site_status(site)
        if info:
            final_results.append(info)

    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"### 机场白嫖情报库 (更新: {now})\n")
        f.write("| 机场名称 | 网址 | 试用流量 | 注册门槛 |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        if not final_results:
            f.write("| 暂无有效数据 | - | - | - |\n")
        for line in final_results:
            # 格式化为 Markdown 表格
            parts = line.replace('✅ ', '').split(' | ')
            f.write(f"| {' | '.join(parts)} |\n")

if __name__ == "__main__":
    main()
