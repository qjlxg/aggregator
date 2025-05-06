import os
import requests

# 引入selenium相关库
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ModuleNotFoundError:
    print("错误：未安装selenium包，请确保在环境中运行 pip install selenium")
    exit(1)

def fetch_links(url):
    """通过selenium抓取所有链接，排除以 https://t.me 开头的链接"""
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        links = set()
        for a in driver.find_elements_by_tag_name('a'):
            href = a.get_attribute('href')
            if href and not href.startswith('https://t.me'):
                links.add(href)
        driver.quit()
        return list(links)
    except Exception as e:
        print(f"抓取页面失败: {e}")
        return []

def is_valid_link(link):
    """测试链接是否有效"""
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    try:
        resp = requests.get(link, headers=headers, timeout=5)
        return resp.status_code == 200
    except:
        return False

def append_links(file_path, links):
    """过滤、验证后，追加到文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    existing = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            existing = set(line.strip() for line in f)
    with open(file_path, 'a', encoding='utf-8') as f:
        for link in set(links):
            if link not in existing and is_valid_link(link):
                f.write(link + '\n')
                existing.add(link)

def main():
    url = os.environ.get('BASE_URL', 'https://t.me/dingyue_center')
    file_path = 'data/subscribes.txt'

    links = fetch_links(url)
    append_links(file_path, links)

    # 提交更新
    os.system('git config --global user.name "github-actions[bot]"')
    os.system('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
    os.system(f'git add {file_path}')
    os.system('git commit -m "自动更新订阅链接" || true')  # 备选：如果无变更不报错

    token = os.environ.get('GITHUB_TOKEN')
    if token:
        os.system(f'git push https://x-access-token:{token}@github.com/qjlxg/362.git main')
    else:
        print("未找到GITHUB_TOKEN，无法推送结果到仓库。")

if __name__ == '__main__':
    main()
