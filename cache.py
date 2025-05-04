import os
import re
import requests

output_file = "data/9.txt"
raw_url = "https://github.com/qjlxg/cheemsar/blob/main/trial.cache"

def extract_api_urls_from_raw(raw_url, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    pattern = re.compile(r'https?://[^\s"]*api/v1/client/subscribe\?token=[^\s"]+')

    try:
        resp = requests.get(raw_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text

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
    extract_api_urls_from_raw(raw_url, output_file)
