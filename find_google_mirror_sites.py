import requests
from bs4 import BeautifulSoup
import re
import os
import urllib.parse # 导入 urllib.parse 模块

def find_google_mirror_sites(search_terms=["google mirror", "google代理", "镜像谷歌"]):
    """
    搜索可能包含 Google 镜像站点的网站。请谨慎使用搜索结果。

    Args:
        search_terms: 用于搜索的关键词列表。

    Returns:
        一个包含搜索结果的列表，每个结果是一个包含标题和链接的字典。
    """

    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

    for term in search_terms:
        try:
            # 使用 DuckDuckGo 搜索，因为它通常对审查较不严格
            url = f"https://duckduckgo.com/html/?q={term}"
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # 检查是否有错误
            soup = BeautifulSoup(response.text, 'html.parser')

            # 查找搜索结果
            search_result_elements = soup.find_all('a', class_='result__a')

            for element in search_result_elements:
                title = element.text.strip()
                link = element['href']
                # 从 DuckDuckGo 的重定向 URL 中提取实际链接
                match = re.search(r"url=([^&]+)", link)
                if match:
                    extracted_link = match.group(1)  # 获取URL编码的链接
                    real_link = urllib.parse.unquote(extracted_link)  # 解码URL
                    results.append({"title": title, "link": real_link})

        except requests.exceptions.RequestException as e:
            print(f"搜索 '{term}' 时出错: {e}")
            results.append({"title": f"Error: {e}", "link": ""})  # 将错误信息添加到结果列表中
        except Exception as e:
            print(f"处理搜索结果时出错: {e}")
            results.append({"title": f"Error: {e}", "link": ""})  # 将错误信息添加到结果列表中
    return results


if __name__ == '__main__':
    # 创建 data 目录（如果不存在）
    if not os.path.exists("data"):
        os.makedirs("data")

    mirror_sites = find_google_mirror_sites()

    with open("data/output.txt", "w") as f:
        if mirror_sites:
            f.write("找到的可能 Google 镜像站点：\n")
            for site in mirror_sites:
                f.write(f"  标题: {site['title']}\n")
                f.write(f"  链接: {site['link']}\n")
                f.write("-" * 20 + "\n")
        else:
            f.write("未找到任何潜在的镜像站点。\n")
        f.write("请谨慎验证这些链接的安全性和有效性.\n")  # 重要的安全提示
