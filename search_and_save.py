import os
import requests
import base64
import time
import re

def main():
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("❌ 错误: 未找到 BOT_TOKEN")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1. 扩大搜索范围：只搜文件名，不限制在 data/ 目录下，排除 fork
    # 如果结果还是少，可以尝试更宽泛的 "valid-domains.txt"
    query = "filename:valid-domains.txt"
    
    unique_domains = set()
    
    # 尝试爬取前 5 页结果（每页 100 条）
    for page in range(1, 6):
        print(f"🔍 正在检索第 {page} 页数据...")
        search_url = f"https://api.github.com/search/code?q={query}&per_page=100&page={page}"
        
        try:
            response = requests.get(search_url, headers=headers)
            if response.status_code == 403:
                print("🚫 触发速率限制，等待 30 秒后重试...")
                time.sleep(30)
                continue
            elif response.status_code != 200:
                print(f"❌ 停止检索: {response.status_code}")
                break
            
            items = response.json().get('items', [])
            if not items:
                print("ℹ️ 没有更多结果了。")
                break
                
            print(f"📂 本页发现 {len(items)} 个候选文件。")

            for item in items:
                repo_name = item['repository']['full_name']
                file_url = item['url']
                
                # 记录一下当前处理的仓库
                file_res = requests.get(file_url, headers=headers)
                if file_res.status_code == 200:
                    content_data = file_res.json()
                    try:
                        raw_text = base64.b64decode(content_data['content']).decode('utf-8', errors='ignore')
                        # 匹配所有 http/https 链接
                        found_links = re.findall(r'https?://[a-zA-Z0-9][-a-zA-Z0-9.]+(?::\d+)?(?:/[^\s]*)?', raw_text)
                        for link in found_links:
                            # 清洗：去掉末尾的引号、括号或斜杠
                            clean = link.strip().rstrip('/').rstrip('"').rstrip("'")
                            if clean:
                                unique_domains.add(clean)
                    except Exception:
                        pass
                
                # 代码搜索 API 极其敏感，必须控制频率
                time.sleep(1.5)
                
        except Exception as e:
            print(f"⚠️ 运行异常: {e}")
            break

    # 保存逻辑
    output_dir = 'data'
    output_file = os.path.join(output_dir, 'all-collected-domains.txt')
    os.makedirs(output_dir, exist_ok=True)
    
    if unique_domains:
        sorted_domains = sorted(list(unique_domains))
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_domains) + '\n')
        print(f"✅ 完成！总计抓取到 {len(unique_domains)} 条唯一链接。")
    else:
        print("📭 未能获取到数据。")

if __name__ == "__main__":
    main()
