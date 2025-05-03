import requests
import re
import random
import time
import os

def get_random_headers():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "close"
    }

def update_proxy_list_file():
    proxies = set()
    # 1. 免费API: https://www.proxy-list.download/api/v1/get?type=http
    try:
        resp = requests.get("https://www.proxy-list.download/api/v1/get?type=http", timeout=10)
        for line in resp.text.splitlines():
            if ':' in line:
                proxies.add("http://" + line.strip())
    except Exception as e:
        print(f"获取proxy-list.download代理失败: {e}")

    # 2. 免费API: https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt
    try:
        resp = requests.get("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", timeout=10)
        for line in resp.text.splitlines():
            if ':' in line:
                proxies.add("http://" + line.strip())
    except Exception as e:
        print(f"获取TheSpeedX代理失败: {e}")

    # 3. 免费API: https://www.proxyscan.io/api/proxy?format=txt&type=http
    try:
        resp = requests.get("https://www.proxyscan.io/api/proxy?format=txt&type=http", timeout=10)
        for line in resp.text.splitlines():
            if ':' in line:
                proxies.add("http://" + line.strip())
    except Exception as e:
        print(f"获取proxyscan.io代理失败: {e}")

    # 4. 静态免费代理列表
    static_list = [
        "http://51.158.68.68:8811",
        "http://185.199.228.110:7492",
        "http://103.152.232.66:8080",
        "http://103.163.13.8:8080",
        "http://103.169.187.146:3125",
        "http://103.178.43.90:8181",
        "http://103.180.113.218:10000",
        "http://103.180.113.218:10001",
        "http://103.180.113.218:10002",
        "http://103.180.113.218:10003"
    ]
    proxies.update(static_list)
    os.makedirs("data", exist_ok=True)
    with open("data/proxy.txt", "w", encoding="utf-8") as f:
        for p in proxies:
            f.write(p + "\n")
    print(f"已更新代理池，共 {len(proxies)} 条，保存在 data/proxy.txt")
    return list(proxies)

def load_proxy_list():
    proxies = []
    if os.path.exists("data/proxy.txt"):
        with open("data/proxy.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    proxies.append(line)
    return proxies

def get_random_proxy(proxy_list):
    if not proxy_list:
        return None
    proxy = random.choice(proxy_list)
    return {"http": proxy, "https": proxy}

def search_and_extract_urls(query, num_results=30, sleep_range=(2, 5), proxy_list=None):
    urls = set()

    # Google
    for start in range(0, num_results, 10):
        g_url = f"https://www.google.com/search?q={query}&start={start}"
        try:
            proxies = get_random_proxy(proxy_list)
            resp = requests.get(g_url, headers=get_random_headers(), proxies=proxies, timeout=10)
            found = re.findall(r'https?://[^\s"\'<>]+', resp.text)
            for u in found:
                if "oss.v2rayse.com/proxies/data" in u:
                    urls.add(u.split('&')[0])
            time.sleep(random.uniform(*sleep_range))
        except Exception as e:
            print(f"Google搜索异常: {e}")
            time.sleep(random.uniform(*sleep_range))

    # Bing
    for first in range(1, num_results+1, 10):
        b_url = f"https://www.bing.com/search?q={query}&first={first}"
        try:
            proxies = get_random_proxy(proxy_list)
            resp = requests.get(b_url, headers=get_random_headers(), proxies=proxies, timeout=10)
            found = re.findall(r'https?://[^\s"\'<>]+', resp.text)
            for u in found:
                if "oss.v2rayse.com/proxies/data" in u:
                    urls.add(u.split('&')[0])
            time.sleep(random.uniform(*sleep_range))
        except Exception as e:
            print(f"Bing搜索异常: {e}")
            time.sleep(random.uniform(*sleep_range))

    return list(urls)

def main():
    query = "https://oss.v2rayse.com/proxies/data"
    print("正在更新免费代理池...")
    proxy_list = update_proxy_list_file()
    print(f"获取到{len(proxy_list)}个代理，将用于搜索。")
    urls = search_and_extract_urls(query, proxy_list=proxy_list)
    os.makedirs("data", exist_ok=True)
    with open("data/u.txt", "w", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")
    print(f"已保存 {len(urls)} 个网址到 data/u.txt")

if __name__ == "__main__":
    main()
