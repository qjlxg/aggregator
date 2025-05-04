import os
import re
import requests
import base64

output_file = "data/9.txt"
github_url = "https://github.com/qjlxg/cheemsar/blob/main/trial.cache"

def extract_api_urls_from_github(github_url, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    # 匹配包含 api/v1/client/subscribe?token= 的网址
    pattern = re.compile(r'https?://[^\s"]*api/v1/client/subscribe\?token=[^\s"]+')

    try:
        resp = requests.get(github_url)
        resp.raise_for_status()
        content = resp.json()['content']
        text = base64.b64decode(content).decode('utf-8')

        urls = []
        for line in text.splitlines():
            found = pattern.findall(line)
            urls.extend(found)

        with open(output_file, "w", encoding="utf-8") as f:
            for url in urls:
                f.write(url + "\n")

        print(f"提取完成，共提取 {len(urls)} 个网址，保存到 {output_file}")

    except Exception as e:
        print(f"处理失败: {e}")

if __name__ == "__main__":
    extract_api_urls_from_github(github_url, output_file)
