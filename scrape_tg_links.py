# scrape_tg_links_requests.py
import requests
from bs4 import BeautifulSoup
import os

channel_url = os.environ.get("TELEGRAM_CHANNEL_URL", "")
output_file = os.path.join("data", "ji2.txt")
data_dir = "data"

# 确保 data 目录存在
if not os.path.exists(data_dir):
    os.makedirs(data_dir)


def scrape_links():
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(channel_url, headers=headers)
        response.raise_for_status()
        print(f"请求成功，状态码：{response.status_code}")

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        message_elements = soup.find_all('div', class_='tgme_post_text') #  修改了选择器

        print(f"找到的消息元素数量: {len(message_elements)}")

        with open(output_file, 'w', encoding='utf-8') as f:
            for message_element in message_elements:
                links = message_element.find_all('a')
                print(f"在这个消息元素中找到的链接数量: {len(links)}")
                for link in links:
                    url = link['href']
                    print(f"提取到的链接: {url}")
                    f.write(url + '\n')

        print(f"Urls saved to {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"请求出错: {e}")
    except Exception as e:
        print(f"解析出错: {e}")


if __name__ == "__main__":
    scrape_links()
