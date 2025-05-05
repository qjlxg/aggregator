import os
import re
import requests
import base64

CLASH_API_cache = os.environ.get("CLASH_API_cache", "").strip()
GIST_PAT = os.environ.get("GIST_PAT", "").strip()
raw_urls_env = os.environ.get("RAW_URLS", "")
raw_urls = [u.strip() for u in raw_urls_env.split(",") if u.strip()]

def fetch_repo_file(api_url, headers):
    try:
        print(f"Fetching from: {api_url}")
        resp = requests.get(api_url, headers=headers, timeout=10)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
            sha = data.get("sha")
            return content, sha
        elif resp.status_code == 404:
            print("文件不存在，将创建新文件")
            return "", None
    except Exception as e:
        print(f"读取仓库文件失败: {e}")
    return "", None

def push_repo_file(api_url, content, sha, headers):
    try:
        payload = {
            "message": "Update subscribes.txt via script",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha
        else:
            payload.pop("sha", None)  # 文件不存在时创建新文件
        resp = requests.put(api_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        print("subscribes.txt 已推送")
    except Exception as e:
        print(f"推送到仓库失败: {e}")

def extract_and_append_unique_urls(raw_urls, api_url, headers):
    pattern = re.compile(r'https?://[^\s"]*api/v1/client/subscribe\?token=[^\s"]+')
    existing_urls = set()
    content, sha = fetch_repo_file(api_url, headers)
    if content:
        for line in content.splitlines():
            existing_urls.add(line.strip())
    new_urls = set()
    for url in raw_urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            text = resp.text
            for line in text.splitlines():
                found = pattern.findall(line)
                new_urls.update(found)
        except Exception as e:
            print(f"处理 {url} 失败: {e}")
    all_urls = existing_urls | new_urls
    result = "\n".join(sorted(all_urls))
    push_repo_file(api_url, result, sha, headers)
    print(f"追加并去重完成，共 {len(all_urls)} 个网址，已推送到私有仓库")

if __name__ == "__main__":
    if not CLASH_API_cache or not GIST_PAT or not raw_urls:
        print("请设置环境变量 CLASH_API_cache、GIST_PAT 和 RAW_URLS")
        exit(1)
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Authorization': f"token {GIST_PAT}"
    }
    extract_and_append_unique_urls(raw_urls, CLASH_API_cache, headers)
