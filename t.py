import requests
import re
import os
import time

def fetch_telegram_subscribe_links(
    channels, max_pages=10, sleep_sec=1.0, out_file="data/t.txt", node_file="data/hy.txt"
):
    sub_pattern = r"https?://[^\s'\"<>]*api/v1/client/subscribe\?token=[\w\-]+"
    node_patterns = [
        r"vmess://[A-Za-z0-9+/=._\-]+",
        r"ss://[A-Za-z0-9+/=._\-]+",
        r"hysteria2://[A-Za-z0-9+/=._\-]+",
        r"trojan://[A-Za-z0-9+/=._\-]+",
        r"vless://[A-Za-z0-9+/=._\-]+"
    ]
    urls = set()
    nodes = set()

    for channel in channels:
        base_url = f"https://t.me/s/{channel}"
        last_id = None
        for _ in range(max_pages):
            url = base_url if last_id is None else f"{base_url}?before={last_id}"
            resp = requests.get(url)
            resp.encoding = resp.apparent_encoding
            html = resp.text

            # 提取订阅链接
            urls.update(re.findall(sub_pattern, html))
            # 提取节点链接
            for pat in node_patterns:
                nodes.update(re.findall(pat, html))

            ids = re.findall(r'data-post="[^/]+/(\d+)"', html)
            if not ids:
                break
            min_id = min(map(int, ids))
            if last_id == min_id:
                break
            last_id = min_id
            time.sleep(sleep_sec)

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for url in sorted(urls):
            f.write(url + "\n")
    print(f"共找到{len(urls)}个订阅链接，已保存到{out_file}")

    # 节点链接去重并保存
    nodes = set(nodes)
    os.makedirs(os.path.dirname(node_file), exist_ok=True)
    with open(node_file, "w", encoding="utf-8") as f:
        for node in sorted(nodes):
            f.write(node + "\n")
    print(f"共找到{len(nodes)}个节点链接，已保存到{node_file}")

    return sorted(urls), sorted(nodes)

def test_urls(urls, timeout=10):
    ok, fail = [], []
    for url in urls:
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                ok.append(url)
            else:
                fail.append(url)
        except Exception:
            fail.append(url)
    print(f"可用: {len(ok)}，不可用: {len(fail)}")
    if fail:
        print("不可用URL：")
        for u in fail:
            print(u)
    return ok, fail

if __name__ == "__main__":
    channels = ["oneclickvpnkeys", "another_channel"]
    urls, nodes = fetch_telegram_subscribe_links(channels, max_pages=10)
    test_urls(urls)
