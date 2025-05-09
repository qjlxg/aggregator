import requests
from bs4 import BeautifulSoup
import re

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
                    real_link = match.group(1)
                    results.append({"title": title, "link": real_link})

        except requests.exceptions.RequestException as e:
            print(f"搜索 '{term}' 时出错: {e}")
        except Exception as e:
            print(f"处理搜索结果时出错: {e}")
    return results


if __name__ == '__main__':
    mirror_sites = find_google_mirror_sites()

    if mirror_sites:
        print("找到的可能 Google 镜像站点：")
        for site in mirror_sites:
            print(f"  标题: {site['title']}")
            print(f"  链接: {site['link']}")
            print("-" * 20)
    else:
        print("未找到任何潜在的镜像站点。")
    print("请谨慎验证这些链接的安全性和有效性.")
