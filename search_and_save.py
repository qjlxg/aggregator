import os
import requests
import base64
import time
import re

def main():
    # 获取 GitHub Actions 传入的 Secret
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("❌ 错误: 环境变量 BOT_TOKEN 为空，请检查 Secrets 设置。")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 搜索全站路径为 data/valid-domains.txt 的文件
    query = "path:data/valid-domains.txt"
    search_url = f"https://api.github.com/search/code?q={query}"
    
    unique_domains = set()
    
    print(f"🔍 正在检索 GitHub 全站数据: {query}...")
    
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code == 403:
            print("🚫 触发 API 速率限制，请稍后再试或检查 Token 权限。")
            return
        elif response.status_code != 200:
            print(f"❌ 搜索失败: {response.status_code}")
            return
        
        items = response.json().get('items', [])
        print(f"📂 发现 {len(items)} 个匹配的仓库文件。")

        for item in items:
            repo_name = item['repository']['full_name']
            file_url = item['url']
            
            print(f"读取中: {repo_name}...")
            
            # 获取内容
            content_res = requests.get(file_url, headers=headers)
            if content_res.status_code == 200:
                data = content_res.json()
                # GitHub API 返回的内容是 Base64 编码的
                try:
                    raw_content = base64.b64decode(data['content']).decode('utf-8')
                    # 提取 URL (支持 http/https)
                    links = re.findall(r'https?://[^\s,>]+', raw_content)
                    for link in links:
                        # 清洗结尾的斜杠或空格
                        clean_link = link.strip().rstrip('/')
                        unique_domains.add(clean_link)
                except Exception as e:
                    print(f"解析 {repo_name} 失败: {e}")
            
            # 间隔 1.5 秒防止被封
            time.sleep(1.5)

    except Exception as e:
        print(f"⚠️ 运行异常: {e}")

    # 结果处理
    output_dir = 'data'
    output_file = os.path.join(output_dir, 'all-collected-domains.txt')
    os.makedirs(output_dir, exist_ok=True)
    
    if unique_domains:
        sorted_domains = sorted(list(unique_domains))
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_domains) + '\n')
        print(f"✅ 抓取成功！总计 {len(sorted_domains)} 个去重链接已保存。")
    else:
        print("📭 未能从搜索结果中提取到任何有效链接。")

if __name__ == "__main__":
    main()
