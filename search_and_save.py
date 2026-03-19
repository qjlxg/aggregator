import os
import requests
import base64
import time

def main():
    # 从环境变量获取 Token (由 GitHub Actions 传入)
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("错误: 未找到环境变量 BOT_TOKEN")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 定义搜索查询：搜索路径为 data/valid-domains.txt 的文件
    # 你也可以加上 extension:txt 或 size:>10 来过滤
    query = "path:data/valid-domains.txt"
    search_url = f"https://api.github.com/search/code?q={query}"
    
    unique_domains = set()
    
    print(f"正在 GitHub 全站搜索: {query}...")
    
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code != 200:
            print(f"搜索失败: {response.status_code}, {response.text}")
            return
        
        items = response.json().get('items', [])
        print(f"找到 {len(items)} 个匹配的文件库。")

        for item in items:
            repo_full_name = item['repository']['full_name']
            file_url = item['url'] # 这是获取文件内容的 API 链接
            
            print(f"正在抓取: {repo_full_name} ...")
            
            # 获取文件内容（通常是 Base64 编码）
            file_res = requests.get(file_url, headers=headers)
            if file_res.status_code == 200:
                content_json = file_res.json()
                raw_content = base_base64_decode(content_json.get('content', ''))
                
                # 处理内容
                for line in raw_content.splitlines():
                    domain = line.strip()
                    if domain and "." in domain: # 简单的域名校验
                        unique_domains.add(domain)
            
            # 遵守 API 速率限制，稍微停顿
            time.sleep(1)

    except Exception as e:
        print(f"运行出错: {e}")

    # 保存结果
    output_file = 'data/all-collected-domains.txt'
    os.makedirs('data', exist_ok=True)
    
    if unique_domains:
        sorted_domains = sorted(list(unique_domains))
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_domains) + '\n')
        print(f"✅ 处理完成！抓取到 {len(unique_domains)} 个唯一域名，保存至 {output_file}")
    else:
        print("❌ 未抓取到任何有效域名数据。")

def base_base64_decode(encoded_str):
    """解码 GitHub API 返回的 Base64 内容"""
    try:
        # 移除换行符
        decoded_bytes = base64.b64decode(encoded_str.replace('\n', ''))
        return decoded_bytes.decode('utf-8')
    except:
        return ""

if __name__ == "__main__":
    main()
