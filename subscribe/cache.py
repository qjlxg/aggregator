
 import os
 import re
 import requests
 import base64
 
 output_file = "data/subscribes.txt"
 raw_urls = [
     "https://raw.githubusercontent.com/qjlxg/cheemsar/main/trial.cache",
     "https://raw.githubusercontent.com/qjlxg/aggregator/main/trial.cache",
     "https://raw.githubusercontent.com/qjlxg/cheemsar-2/main/trial.cache",
 ]
 CLASH_API = os.environ.get("CLASH_API", "").strip()
 GIST_PAT = os.environ.get("GIST_PAT", "").strip()
 
 def extract_and_append_unique_urls(raw_urls, output_file):
     os.makedirs(os.path.dirname(output_file), exist_ok=True)
 
 raw_urls_env = os.environ.get("RAW_URLS", "")
 raw_urls = [u.strip() for u in raw_urls_env.split(",") if u.strip()]
 
 def fetch_repo_file(api_url, headers):
     try:
         resp = requests.get(api_url, headers=headers, timeout=10)
         if resp.status_code == 200:
             data = resp.json()
             content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
             sha = data.get("sha")
             return content, sha
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
         resp = requests.put(api_url, json=payload, headers=headers, timeout=10)
         resp.raise_for_status()
         print("subscribes.txt 已推送")
     except Exception as e:
         print(f"推送到仓库失败: {e}")
 
 def extract_and_append_unique_urls(raw_urls, api_url, headers):
     pattern = re.compile(r'https?://[^\s"]*api/v1/client/subscribe\?token=[^\s"]+')
 
     # 读取已有的网址（去重用）
     existing_urls = set()
     if os.path.exists(output_file):
         with open(output_file, "r", encoding="utf-8") as f:
             for line in f:
                 existing_urls.add(line.strip())
     content, sha = fetch_repo_file(api_url, headers)
     if content:
         for line in content.splitlines():
             existing_urls.add(line.strip())
 
     new_urls = set()
     for url in raw_urls:
def extract_and_append_unique_urls(raw_urls, output_file):
         except Exception as e:
             print(f"处理 {url} 失败: {e}")
 
     # 合并去重
     all_urls = existing_urls | new_urls
     result = "\n".join(sorted(all_urls))
 
     # 保存去重后的所有网址
     with open(output_file, "w", encoding="utf-8") as f:
         for url in sorted(all_urls):
             f.write(url + "\n")
 
     print(f"追加并去重完成，共 {len(all_urls)} 个网址，已保存到 {output_file}")
     push_repo_file(api_url, result, sha, headers)
     print(f"追加并去重完成，共 {len(all_urls)} 个网址，已推送到私有仓库")
 
 if __name__ == "__main__":
     extract_and_append_unique_urls(raw_urls, output_file)
     if not CLASH_API or not GIST_PAT or not raw_urls:
         print("请设置环境变量 CLASH_API、GIST_PAT 和 RAW_URLS")
         exit(1)
     headers = {
         'User-Agent': 'Mozilla/5.0',
         'Authorization': f"token {GIST_PAT}"
     }
     extract_and_append_unique_urls(raw_urls, CLASH_API, headers)
