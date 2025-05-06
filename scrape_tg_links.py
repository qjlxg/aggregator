import os
import requests
from bs4 import BeautifulSoup

def fetch_links(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if not href.startswith('https://t.me'):
                links.add(href)
        return list(links)
    except Exception as e:
        print(f"抓取网页失败：{e}")
        return []

def validate_link(link):
    try:
        resp = requests.head(link, timeout=5)
        return resp.status_code == 200
    except:
        return False

def main():
    url = os.environ.get('BASE_URL', 'https://t.me/dingyue_center')
    output_file = 'data/subscribes.txt'
    links = fetch_links(url)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    existing_links = set()
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_links = set(line.strip() for line in f)

    new_links = []
    for link in links:
        if link not in existing_links and validate_link(link):
            new_links.append(link)

    if new_links:
        with open(output_file, 'a', encoding='utf-8') as f:
            for link in new_links:
                f.write(link + '\n')

    # 自动提交推送
    if 'GITHUB_TOKEN' in os.environ:
        os.system('git config --global user.name "github-actions[bot]"')
        os.system('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
        os.system(f'git add {output_file}')
        os.system('git commit -m "自动更新订阅链接" || true')
        os.system(f'git push https://x-access-token:{os.environ["GITHUB_TOKEN"]}@github.com/qjlxg/362.git main')

if __name__ == '__main__':
    main()
