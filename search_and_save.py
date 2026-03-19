import os
import requests
import base64
import time
import re

def main():
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("❌ 错误: 未找到 BOT_TOKEN 环境变量")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 优化查询语句：搜索文件名，排除 fork 仓库，增加搜索成功率
    # 注意：GitHub API 搜索代码时，如果查询太短可能会失败，这里增加 filename 约束
    query = "filename:valid-domains.txt path:data"
    search_url = f"https://api.github.com/search/code?q={query}&per_page=100"
    
    unique_domains = set()
    
    print(f"🔍 正在尝试检索 GitHub 数据: {query}...")
    
    try:
        response = requests.get(search_url, headers=headers)
        
        # 打印详细错误信息
        if response.status_code == 403:
            print("🚫 触发速率限制或权限不足。请确保您的 Token 具有 'repo' 和 'read:discussion' 权限。")
            return
        elif response.status_code != 200:
            print(f"❌ API 报错: {response.status_code} - {response.text}")
            return
        
        search_results = response.json()
        items = search_results.get('items', [])
        
        print(f"📂 本次 API 返回了 {len(items)} 个候选文件。")

        for item in items:
            repo_name = item['repository']['full_name']
            file_url = item['url']
            
            # 这里的 log 能帮你在 Actions 里看到进度
            print(f"正在读取仓库 [{repo_name}] 中的文件...")
            
            file_res = requests.get(file_url, headers=headers)
            if file_res.status_code == 200:
                content_data = file_res.json()
                try:
                    # 解码 Base64
                    raw_text = base64.b64decode(content_data['content']).decode('utf-8')
                    # 匹配 http/https 链接
                    found_links = re.findall(r'https?://[a-zA-Z0-9][-a-zA-Z0-9.]+(?::\d+)?(?:/[^\s]*)?', raw_text)
                    for link in found_links:
                        # 移除末尾的斜杠和空白
                        clean = link.strip().rstrip('/')
                        if clean:
                            unique_domains.add(clean)
                except Exception as e:
                    print(f"解析 {repo_name} 内容出错: {e}")
            
            # 稍微停顿，防止被 GitHub 临时封禁
            time.sleep(2)

    except Exception as e:
        print(f"⚠️ 运行过程中出现异常: {e}")

    # 保存逻辑
    output_dir = 'data'
    output_file = os.path.join(output_dir, 'all-collected-domains.txt')
    os.makedirs(output_dir, exist_ok=True)
    
    if unique_domains:
        # 排序
        final_list = sorted(list(unique_domains))
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_list) + '\n')
        print(f"✅ 大功告成！总计抓取到 {len(final_list)} 条唯一链接，已保存至 {output_file}")
    else:
        print("📭 依然未找到匹配项。建议检查 Token 是否为 Personal Access Token (Classic) 且权限完整。")

if __name__ == "__main__":
    main()
