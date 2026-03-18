import requests
import base64
import time
import os
from datetime import datetime

# 从 GitHub Secrets 中读取 API Key
API_KEY = os.getenv("HUNTER_API_KEY")
SEARCH_QUERY = 'web.body="/theme/default/assets/components.chunk.css"'
SAVE_FILE = "hunter_results.txt"
PAGE_SIZE = 100 

def fetch_all_domains():
    if not API_KEY:
        print("错误: 未在环境变量中找到 HUNTER_API_KEY")
        return

    # 1. 尝试使用纯日期格式 YYYY-MM-DD (去掉时分秒)
    # 这是大多数网络安全 API (如 FOFA/Hunter) 最喜欢的格式
    start_time = "2026-01-01"
    end_time = datetime.now().strftime("%Y-%m-%d")

    # 2. Base64 编码查询词
    encoded_query = base64.urlsafe_b64encode(SEARCH_QUERY.encode()).decode()
    all_domains = set()
    page = 1
    
    print(f"开始抓取结果... 时间范围: {start_time} 至 {end_time}")

    while True:
        # 构造 URL
        url = (
            f"https://api.hunter.how/search?api-key={API_KEY}"
            f"&query={encoded_query}"
            f"&page={page}"
            f"&page_size={PAGE_SIZE}"
            f"&start_time={start_time}"
            f"&end_time={end_time}"
        )
        
        try:
            # 打印请求的 URL (隐藏 API KEY 的一部分) 用于调试
            debug_url = url.replace(API_KEY, API_KEY[:6] + "***")
            print(f"请求 URL: {debug_url}")
            
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if data.get('code') == 200:
                result_data = data.get('data', {})
                items = result_data.get('list', []) if result_data else []
                
                if not items:
                    print("未发现更多数据，抓取结束。")
                    break
                
                for item in items:
                    domain = item.get('domain')
                    if domain:
                        all_domains.add(domain)
                
                print(f"第 {page} 页完成，当前累计: {len(all_domains)}")
                
                # 判断是否翻页结束
                total = result_data.get('total', 0)
                if len(all_domains) >= total or len(items) < PAGE_SIZE:
                    break
                
                page += 1
                time.sleep(2) 
            else:
                print(f"API 错误提示: {data.get('message')} (Code: {data.get('code')})")
                break
        except Exception as e:
            print(f"请求发生异常: {e}")
            break

    # 3. 写入文件
    if all_domains:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            for d in sorted(list(all_domains)):
                f.write(d + "\n")
        print(f"任务完成！共保存 {len(all_domains)} 个域名到 {SAVE_FILE}")
    else:
        print("警告：结果为空。如果格式依然错误，请尝试将 start_time 设为更近的日期。")

if __name__ == "__main__":
    fetch_all_domains()
