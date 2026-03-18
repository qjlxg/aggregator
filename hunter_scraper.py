import requests
import base64
import time
import os

# 从 GitHub Secrets 中读取 API Key，保证安全
API_KEY = os.getenv("HUNTER_API_KEY")
SEARCH_QUERY = 'web.body="/theme/default/assets/components.chunk.css"'
SAVE_FILE = "hunter_results.txt"
PAGE_SIZE = 100 

def fetch_all_domains():
    if not API_KEY:
        print("错误: 未在环境变量中找到 HUNTER_API_KEY")
        return

    encoded_query = base64.urlsafe_b64encode(SEARCH_QUERY.encode()).decode()
    all_domains = set()
    page = 1
    
    print(f"开始抓取结果...")

    while True:
        url = f"https://api.hunter.how/search?api-key={API_KEY}&query={encoded_query}&page={page}&page_size={PAGE_SIZE}"
        try:
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if data.get('code') == 200:
                items = data['data'].get('list', [])
                if not items:
                    break
                
                for item in items:
                    domain = item.get('domain')
                    if domain:
                        all_domains.add(domain)
                
                print(f"第 {page} 页抓取完成，目前累计 {len(all_domains)} 个域名")
                
                if len(items) < PAGE_SIZE:
                    break
                
                page += 1
                time.sleep(2) # 避免触发频率限制
            else:
                print(f"API 错误: {data.get('message')}")
                break
        except Exception as e:
            print(f"请求异常: {e}")
            break

    if all_domains:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            for d in sorted(list(all_domains)):
                f.write(d + "\n")
        print(f"成功保存 {len(all_domains)} 个域名到 {SAVE_FILE}")

if __name__ == "__main__":
    fetch_all_domains()
