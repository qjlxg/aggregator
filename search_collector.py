from bs4 import BeautifulSoup
import requests

def extract_google_links(query):
    url = "https://www.google.com/search"
    params = {"q": query, "num": "100"}
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    resp = requests.get(url, params=params, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")

    links = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        if href.startswith("/url?q="):
            real = href.split("/url?q=")[1].split("&")[0]
            links.add(real)

    return links

if __name__ == "__main__":
    query = '"v2board" "assets/umi.js"'
    results = extract_google_links(query)

    with open("google_results.txt", "w", encoding="utf-8") as f:
        for link in results:
            f.write(link + "\n")

    print(f"已保存 {len(results)} 个网址到 google_results.txt")
