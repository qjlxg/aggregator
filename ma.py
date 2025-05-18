import requests
import argparse
from base64 import b64encode
import string

def fetch_proxies_from_url(url):
    "https://github.com/0x24a/FreeNodes/raw/refs/heads/main/subs/main.txt",
    从单个网址获取代理列表。
    假设代理数据是文本格式，每行一个代理。
    """
    try:
        response = requests.get(url, timeout=10)  # 设置10秒超时
        response.raise_for_status()  # 如果HTTP请求失败，抛出异常
        proxies = response.text.splitlines()  # 按行分割获取代理
        print(f"- Fetched {len(proxies)} proxies from {url}")
        return proxies
    except requests.RequestException as e:
        print(f"- Failed to fetch from {url}: {e}")
        return []

def save_proxies(proxies, filename):
    """
    将代理列表以Base64编码格式保存到文件中。
    """
    result = b64encode("\n".join(proxies).encode("utf-8")).decode()
    with open(filename, "w+") as f:
        f.write(result)
    print(f"Saved to {filename}")

# 设置命令行参数解析
parser = argparse.ArgumentParser(description="Fetch proxies from multiple URLs and save them.")
parser.add_argument("urls", nargs="+", help="List of URLs to fetch proxies from")
args = parser.parse_args()

# 获取所有代理并去重
proxies = []
for url in args.urls:
    proxies += fetch_proxies_from_url(url)

print("Merging proxies")
number_before = len(proxies)
proxies = list(set(proxies))  # 去重
print(f"Number of proxies: {number_before} -> {len(proxies)}")

# 保存所有代理到主文件
save_proxies(proxies, "subs/main.txt")

# 按协议分类代理
protocols = {}
for proxy in proxies:
    protocol = proxy.split("://", 1)[0]  # 提取协议部分
    if protocol in protocols:
        protocols[protocol].append(proxy)
    else:
        protocols[protocol] = [proxy]

# 保存按协议分类的代理
for protocol, proxy_list in protocols.items():
    if not protocol or len(protocol) > 24 or " " in protocol:
        continue
    if not all(c in string.digits + string.ascii_letters for c in protocol):
        continue
    print(f"Saving {protocol.upper()} proxies")
    save_proxies(proxy_list, f"subs/{protocol.lower()}.txt")

print("Done!")
