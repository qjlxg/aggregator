import requests
from bs4 import BeautifulSoup
import re
import time

def get_urls_from_html(html):
    """从HTML中提取URLs"""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    all_urls = []
    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        all_urls.extend([url for url in urls if not url.startswith(('https://t.me', 'http://t.me', 't.me'))])

    return all_urls

def test_url_connectivity(url):
    """测试URL是否可连通"""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code < 400
    except requests.RequestException:
        return False

def get_next_page_url(html):
    """从HTML中提取下一页的URL（如果有）"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more:
        return 'https://t.me' + load_more['href']
    return None


def main():
    base_url = 'https://t.me/s/dingyue_center'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    }

    all_urls = []
    current_url = base_url
    page_count = 0
    max_pages = 10  # 设置最大抓取页数，防止无限循环

    try:
        while current_url and page_count < max_pages:
            print(f"正在抓取页面: {current_url}")
            response = requests.get(current_url, headers=headers, timeout=10)
            response.raise_for_status()

            all_urls.extend(get_urls_from_html(response.text))

            next_page_url = get_next_page_url(response.text)
            current_url = next_page_url
            page_count += 1
            time.sleep(38)  # 礼貌地延迟一段时间，避免请求过快

        unique_urls = list(set(all_urls))
        valid_urls = [url for url in unique_urls if test_url_connectivity(url)]

        print(f"共抓取 {page_count} 页")
        print(f"找到的有效URL数量: {len(valid_urls)}")

        with open('data/ji.txt', 'w', encoding='utf-8') as f:
            for url in valid_urls:
                f.write(url + '\n')

        print("URL已保存到 data/ji2.txt")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == '__main__':
    main()
