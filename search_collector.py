import requests
from bs4 import BeautifulSoup
import urllib.parse

def google_search(query, pages=3):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    results = set()

    for page in range(pages):
        start = page * 10
        url = "https://www.google.com/search"
        params = {"q": query, "start": start}

        resp = requests.get(url, params=params, headers=headers)
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.select("a"):
            href = a.get("href", "")
            if href.startswith("/url?q="):
                real_url = href.split("/url?q=")[1].split("&")[0]
                real_url = urllib.parse.unquote(real_url)
                results.add(real_url)

    return results


if __name__ == "__main__":
    query = '"v2board" "assets/umi.js"'
    urls = google_search(query, pages=5)

    with open("google_results.txt", "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")

    print(f"已保存 {len(urls)} 个完整 URL 到 google_results.txt")
