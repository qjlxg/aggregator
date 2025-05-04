import os
import re
import requests

output_file = "data/subscribes.txt"
raw_url = "https://github.com/qjlxg/cheemsar/blob/main/trial.cache",
          "https://github.com/qjlxg/cheemsar-2/blob/main/trial.cache",

def extract_and_append_unique_urls(raw_url, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    pattern = re.compile(r'https?://[^\s"]*api/v1/client/subscribe\?token=[^\s"]+')

    # 读取已有的网址（去重用）
    existing_urls = set()
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                existing_urls.add(line.strip())

    # 获取新网址
    try:
        resp = requests.get(raw_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text

        new_urls = set()
        for line in text.splitlines():
            found = pattern.findall(line)
            new_urls.update(found)

        # 合并去重
        all_urls = existing_urls | new_urls

        # 保存去重后的所有网址
        with open(output_file, "w", encoding="utf-8") as f:
            for url in sorted(all_urls):
                f.write(url + "\n")

        print(f"追加并去重完成，共 {len(all_urls)} 个网址，已保存到 {output_file}")

    except Exception as e:
        print(f"处理失败: {e}")

if __name__ == "__main__":
    extract_and_append_unique_urls(raw_url, output_file)
