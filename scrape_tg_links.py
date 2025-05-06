import os
import requests
from bs4 import BeautifulSoup

def fetch_links(url):
    """从指定 URL 抓取所有链接，排除以 'https://t.me' 开头的链接"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 如果请求失败，抛出异常
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if not a['href'].startswith('https://t.me')]
        return links
    except requests.RequestException as e:
        print(f"无法获取 {url}: {e}")
        return []

def is_valid_link(link):
    """测试链接是否有效（返回状态码 200）"""
    try:
        response = requests.head(link, allow_redirects=True, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def append_to_file(file_path, new_links):
    """将新链接追加到文件中，避免重复"""
    # 读取现有链接
    existing_links = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            existing_links = set(line.strip() for line in f if line.strip())

    # 过滤并追加新链接
    with open(file_path, 'a', encoding='utf-8') as f:
        for link in new_links:
            if link not in existing_links and is_valid_link(link):
                f.write(link + '\n')
                existing_links.add(link)

def main():
    # 从环境变量获取配置
    base_url = os.environ.get('BASE_URL', 'https://t.me/dingyue_center')  # 默认值仅用于本地测试
    file_path = 'data/subscribes.txt'
    
    # 抓取链接并处理
    links = fetch_links(base_url)
    unique_links = list(set(links))  # 去重
    append_to_file(file_path, unique_links)
    
    # 配置 Git 并推送
    os.system('git config --global user.name "github-actions[bot]"')
    os.system('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
    os.system(f'git add {file_path}')
    os.system('git commit -m "Update subscribes.txt with new links" || echo "No changes to commit"')
    os.system(f'git push https://x-access-token:{os.environ["GITHUB_TOKEN"]}@github.com/qjlxg/362.git main')

if __name__ == '__main__':
    main()
