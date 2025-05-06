import requests
from bs4 import BeautifulSoup
import re

def get_urls_from_html(html):
    """从HTML中提取URLs"""
    soup = BeautifulSoup(html, 'html.parser')
    messages = soup.find_all('div', class_='tgme_widget_message_text')
    all_urls = []
    for message in messages:
        urls = re.findall(r'https?://[^\s]+', message.get_text())
        all_urls.extend([url for url in urls if not url.startswith('https://t.me') and not url.startswith('http://t.me')])
    return all_urls

def test_url_connectivity(url):
    """测试URL是否可连通"""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code < 400
    except requests.RequestException:
        return False

def main():
    url = 'https://t.me/s/jichang_list'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        all_urls = get_urls_from_html(response.text)
        unique_urls = list(set(all_urls))
        valid_urls = [url for url in unique_urls if test_url_connectivity(url)]
        with open('data/ji.txt', 'w') as f:
            for url in valid_urls:
                f.write(url + '\n')
    else:
        print(f"Failed to retrieve page. Status code: {response.status_code}")

if __name__ == '__main__':
    main()
