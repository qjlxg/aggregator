import requests
import time
import os

def search_urlscan():
    # 使用引号包裹路径，并去掉可能导致 400 错误的通配符
    queries = [
        'request.url:"/theme/Rocket/assets/"',
        'request.url:"/theme/Aurora/static/"',
        'page.content:"v2board"',
        'filename:"layouts__index.async.js"'
    ]
    
    headers = {
        'Content-Type': 'application/json',
    }
    
    all_urls = set()

    for q in queries:
        print(f"[*] 正在尝试检索: {q}")
        # 使用 params 传参，requests 库会自动处理 URL 编码
        params = {
            'q': q,
            'size': 100
        }
        
        try:
            response = requests.get(
                'https://urlscan.io/api/v1/search/', 
                headers=headers, 
                params=params, 
                timeout=20
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                for r in results:
                    url = r.get('page', {}).get('url')
                    if url:
                        all_urls.add(url)
                print(f"[+] 成功获取 {len(results)} 条原始记录")
            elif response.status_code == 400:
                print(f"[!] 语法错误 (400): 请检查查询语句 -> {q}")
            else:
                print(f"[!] 错误 {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"[!] 请求异常: {e}")
        
        time.sleep(2) # 避免频率过快
        
    return all_urls

if __name__ == "__main__":
    found_assets = search_urlscan()
    # 后面接之前的 verify_target 逻辑...
