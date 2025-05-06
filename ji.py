import requests
from bs4 import BeautifulSoup
import re

def get_urls_from_html(html):
    """从HTML中提取URLs"""
    soup = BeautifulSoup(html, 'html.parser')
    # 查找所有可能的包含链接的元素。
    # tgme_widget_message_text 是主要的，但为了更完整，可以寻找其他可能的容器
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',  # 包含图片和链接的消息
        'tgme_widget_message_video',  #包含视频和链接的消息
        'tgme_widget_message_document',  # 包含文件和链接的消息
        'tgme_widget_message_poll',   # 包含投票和链接的消息
    ])

    all_urls = []
    for target in targets:
        # 提取文本内容，用于查找链接
        text = target.get_text(separator=' ', strip=True) # 使用空格作为分隔符

        # 改进的 URL 匹配，考虑更广泛的 URL 格式
        urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)

        # 过滤掉 Telegram 自身的链接
        all_urls.extend([url for url in urls if not url.startswith(('https://t.me', 'http://t.me', 't.me'))])

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

    try:
        response = requests.get(url, headers=headers, timeout=10) # 添加超时，防止卡住
        response.raise_for_status()  # 检查HTTP状态码, 如果不是200, 抛出异常

        all_urls = get_urls_from_html(response.text)
        unique_urls = list(set(all_urls))
        valid_urls = [url for url in unique_urls if test_url_connectivity(url)]

        print(f"找到的有效URL数量: {len(valid_urls)}")  # 打印找到的链接数量

        with open('data/ji.txt', 'w', encoding='utf-8') as f:  # 显式指定编码为 UTF-8
            for url in valid_urls:
                f.write(url + '\n')

        print("URL已保存到 data/ji.txt")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == '__main__':
    main()
