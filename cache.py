import os
import re
import requests

# 输出文件路径
output_file = "data/9.txt"
url = "https://github.com/qjlxg/cheemsar/blob/main/trial.cache"  # 替换为你的URL

def extract_sub_urls_from_url(url, output_file):
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 正则表达式匹配 sub_url 后的网址
    sub_url_pattern = re.compile(r"sub_url\s+([^\s]+)")

    extracted_urls = []

    try:
        # 从URL读取内容
        response = requests.get(url)
        response.raise_for_status()  # 检查请求是否成功

        # 从文本中提取 sub_url
        for line in response.text.splitlines():
            match = sub_url_pattern.search(line)
            if match:
                extracted_urls.append(match.group(1))

        # 将提取的网址写入输出文件
        with open(output_file, "w", encoding="utf-8") as f:
            for url in extracted_urls:
                f.write(url + "\n")

        print(f"提取完成，共提取 {len(extracted_urls)} 个网址，保存到 {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"从URL读取内容失败: {e}")
    except Exception as e:
        print(f"处理内容失败: {e}")

if __name__ == "__main__":
    extract_sub_urls_from_url(url, output_file)
