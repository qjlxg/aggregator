import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import time

# 定义需要检查的协议列表
protocols = ['vmess://', 'ss://', 'hysteria2://', 'trojan://', 'vless://']

# 检查文本是否包含任一协议
def contains_protocol(text):
    """检查给定的文本是否包含指定的协议"""
    return any(protocol in text for protocol in protocols)

# 下载并检查网页内容
def download_and_check(url, retries=3):
    """
    下载网页内容，检查是否包含协议，并保存到文件
    参数:
        url (str): 要处理的网页 URL
        retries (int): 最大重试次数，默认为 3
    """
    # 设置伪装的 User-Agent 请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for attempt in range(retries):
        try:
            # 发送 GET 请求，设置超时为 10 秒
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # 检查请求是否成功
            
            # 解析 HTML，提取 <body> 内容
            soup = BeautifulSoup(response.text, 'html.parser')
            body = soup.body
            if body:
                body_text = body.get_text()
                if contains_protocol(body_text):
                    # 如果包含协议，追加写入 data/t.txt 文件
                    with open('data/t.txt', 'a', encoding='utf-8') as f:
                        f.write(f"URL: {url}\n{body_text}\n\n")
                    print(f"已保存 {url} 的内容")
                else:
                    print(f"{url} 未包含指定协议")
            else:
                print(f"{url} 无 <body> 内容")
            break  # 成功后跳出重试循环
        except requests.exceptions.RequestException as e:
            print(f"处理 {url} 时出错 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2)  # 失败后等待 2 秒再重试
            else:
                print(f"处理 {url} 失败，跳过")

# 定义 URL 列表
urls = [
    'https://github.com/Alvin9999/new-pac/wiki/ss免费账号',
    'https://github.com/freefq/free',
    'https://github.com/Jsnzkpg/Jsnzkpg',
    'https://www.v2ex.com/',
    'https://www.reddit.com/r/VPN/',
    'https://www.shadowsocks.org/',
    'https://www.v2ray.com/',
    'https://trojan-gfw.github.io/trojan/',
    'https://hysteria.network/',
    'https://twitter.com/',
    'https://t.me/s/v2rayNG_VPN'
]

# 主程序入口
if __name__ == "__main__":
    # 使用多线程处理 URL 列表
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(download_and_check, urls)
