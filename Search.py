import requests
from bs4 import BeautifulSoup

# 定义需要检查的协议列表
protocols = ['vmess://', 'ss://', 'hysteria2://', 'trojan://', 'vless://']

# 检查文本是否包含任一协议
def contains_protocol(text):
    for protocol in protocols:
        if protocol in text:
            return True
    return False

# 下载网页并处理内容
def download_and_check(url):
    try:
        # 发送HTTP GET请求，设置超时为10秒
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 如果请求失败，抛出异常
        
        # 解析HTML，提取body内容
        soup = BeautifulSoup(response.text, 'html.parser')
        body = soup.body
        if body:
            body_text = body.get_text()  # 获取body的纯文本内容
            if contains_protocol(body_text):
                # 如果包含协议，追加写入data/t.txt文件
                with open('data/t.txt', 'a', encoding='utf-8') as f:
                    f.write(f"URL: {url}\n")
                    f.write(body_text)
                    f.write("\n\n")  # 添加分隔符以便区分不同网页内容
                print(f"已保存 {url} 的内容")
    except Exception as e:
        print(f"处理 {url} 时出错: {e}")


urls = [
    
    'https://www.v2ex.com/',
    'https://www.reddit.com/r/VPN/',
    'https://www.shadowsocks.org/',
    'https://www.v2ray.com/',
    'https://trojan-gfw.github.io/trojan/',
    'https://hysteria.network/',
    'https://twitter.com/',
    'https://t.me/s/v2rayNG_VPN',
    'http://example.com/page2',
    # 在此处添加更多URL
]

# 遍历URL列表并处理
for url in urls:
    download_and_check(url)
