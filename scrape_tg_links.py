import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def fetch_links(url):
    """从指定 URL 抓取所有动态加载的链接，排除以 'https://t.me' 开头的链接"""
    try:
        options = Options()
        options.add_argument('--headless')  # 无头模式
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        links = [a.get_attribute('href') for a in driver.find_elements_by_tag_name('a') 
                 if a.get_attribute('href') and not a.get_attribute('href').startswith('https://t.me')]
        driver.quit()
        return links
    except Exception as e:
        print(f"抓取 {url} 时出错: {e}")
        return []

def is_valid_link(link):
    """测试链接是否有效（返回状态码 200）"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(link, headers=headers, allow_redirects=True, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def append_to_file(file_path, new_links):
    """将新链接追加到文件中，避免重复"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    existing_links = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            existing_links = set(line.strip() for line in f if line.strip())
    with open(file_path, 'a', encoding='utf-8') as f:
        for link in new_links:
            if link not in existing_links and is_valid_link(link):
                f.write(link + '\n')
                existing_links.add(link)

def main():
    base_url = os.environ.get('BASE_URL', 'https://t.me/dingyue_center')
    file_path = 'data/subscribes.txt'
    
    links = fetch_links(base_url)
    unique_links = list(set(links))  # 去重
    append_to_file(file_path, unique_links)
    
    os.system('git config --global user.name "github-actions[bot]"')
    os.system('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
    os.system(f'git add {file_path}')
    os.system('git commit -m "Update subscribes.txt with new links" || echo "No changes to commit"')
    
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        os.system(f'git push https://x-access-token:{github_token}@github.com/qjlxg/362.git main')
    else:
        print("错误：未找到 GITHUB_TOKEN，请检查 GitHub Actions 配置")

if __name__ == '__main__':
    try:
        from selenium import webdriver
    except ModuleNotFoundError:
        print("错误：Selenium 未安装，请确保在环境中运行 'pip install selenium'")
        exit(1)
    main()
