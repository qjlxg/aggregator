import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

TRIAL_CFG_PATH = 'trial.cfg'
MAX_WORKERS = 8  # 并发线程数

def read_trial_cfg(path):
    urls = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                urls.append(line)
        print(f"共读取到 {len(urls)} 个网址")
    except Exception as e:
        print(f"读取 {path} 失败: {e}")
    return urls

def fetch_url(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return url, resp.status_code
    except Exception as e:
        return url, None

def main():
    urls = read_trial_cfg(TRIAL_CFG_PATH)
    if not urls:
        print("没有可用网址，退出。")
        return

    valid_urls = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url, result = future.result()
            if result == 200:
                print(f"{url}: 可用")
                valid_urls.append(url)
            else:
                print(f"{url}: 不可用（已过滤）")

    # 覆盖写回 trial.cfg，只保留可用网址
    with open(TRIAL_CFG_PATH, 'w', encoding='utf-8') as f:
        for url in valid_urls:
            f.write(f"{url}\n")
    print(f"检测完成，trial.cfg 已只保留可用网址，共 {len(valid_urls)} 条。")

if __name__ == "__main__":
    main()
