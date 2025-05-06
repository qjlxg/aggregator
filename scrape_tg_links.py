from bs4 import BeautifulSoup
import requests
import re
import os
import time

# Configuration
BASE_URL = 'https://t.me/s/dingyue_center'  # Use /s/ format for public channel access
DATA_DIR = 'data'
OUTPUT_FILE = os.path.join(DATA_DIR, 't.txt')
MAX_PAGES = 10  # Maximum number of pages to scrape

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Request headers
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

def fetch_page(url):
    """Fetch the HTML content of a page."""
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Request failed with status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Request exception: {e}")
        return None

def extract_links(html):
    """Extract subscription links from HTML content."""
    pattern = r'https?://[^\s\'"<>]+'
    all_urls = re.findall(pattern, html)
    target_links = [url for url in all_urls if '/api/v1/client/subscribe?token=' in url]
    print(f"Sample links from page source: {all_urls[:5]}")  # Debug: print first 5 links
    return target_links

def test_url(url):
    """Test if a URL is valid by checking its HTTP status."""
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def get_next_page_url(html, current_url):
    """Find the URL of the next page."""
    soup = BeautifulSoup(html, 'html.parser')
    next_page_link = soup.find('a', {'class': 'tgme_pagination_next'})
    return next_page_link['href'] if next_page_link and 'href' in next_page_link.attrs else None

def main():
    """Main function to scrape and save subscription links."""
    current_url = BASE_URL
    collected_links = set()  # Use a set to avoid duplicates
    page_count = 0

    while current_url and page_count < MAX_PAGES:
        print(f"Scraping page: {current_url}")
        html = fetch_page(current_url)
        if not html:
            print("Page fetch failed, skipping.")
            break

        links = extract_links(html)
        print(f"Found {len(links)} target links.")

        for link in links:
            if link not in collected_links:
                print(f"Testing link: {link}")
                if test_url(link):
                    print(f"Link is valid, saving: {link}")
                    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                        f.write(link + '\n')
                    collected_links.add(link)
                else:
                    print(f"Link is invalid, skipping: {link}")
                time.sleep(0.5)  # Avoid rate limiting

        # Move to the next page
        current_url = get_next_page_url(html, current_url)
        page_count += 1
        time.sleep(1)  # Polite scraping delay

    print(f"Completed, collected {len(collected_links)} valid links.")

    # Create an empty file if it doesn't exist
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w') as f:
            pass

if __name__ == '__main__':
    main()
