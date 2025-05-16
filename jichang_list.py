import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User-Agent pool
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
]

def is_valid_hostname(hostname):
    """Check if the hostname is valid according to domain name rules."""
    if not hostname or len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]
    allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(label) for label in hostname.split("."))

def is_valid_url(url):
    """Validate the URL by checking its structure and hostname."""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    if not is_valid_hostname(parsed.netloc):
        return False
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def clean_url(url):
    """Remove trailing punctuation from the URL."""
    while url and url[-1] in '.,;:!?)':
        url = url[:-1]
    return url

def get_urls_from_html(html):
    """Extract and clean URLs from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set()

    for target in targets:
        # Extract from <a> tags
        for a_tag in target.find_all('a', href=True):
            href = clean_url(a_tag['href'].rstrip('/'))
            if is_valid_url(href):
                urls.add(href)
            else:
                logging.debug(f"Invalid URL from <a> tag discarded: {href}")

        # Extract from text content
        text = target.get_text(separator=' ', strip=True)
        found_urls_in_text = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text)
        for url_in_text in found_urls_in_text:
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text
            url_in_text = clean_url(url_in_text.rstrip('/'))
            if is_valid_url(url_in_text):
                urls.add(url_in_text)
            else:
                logging.debug(f"Invalid URL from text discarded: {url_in_text}")
    return list(urls)

def test_url_connectivity(url, timeout=10):
    """Test if the URL is connectable."""
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_next_page_url(html):
    """Extract the next page URL from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more and load_more.has_attr('href'):
        return 'https://t.me' + load_more['href']
    return None

def fetch_page(url, timeout=15, max_retries=3):
    """Fetch page content with retries and random User-Agent."""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch {url} on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 12 + attempt * 2))
            else:
                logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None
    return None

def save_urls_to_file(urls, filename='data/jichang_list.txt'):
    """Save URLs to a file."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in sorted(list(urls)):
                f.write(url + '\n')
        logging.info(f"URLs saved to {filename} (count: {len(urls)})")
    except IOError as e:
        logging.error(f"Failed to save URLs to {filename}: {e}")

def main(start_urls, max_pages_per_source=90, max_workers=10):
    """Main function to control the scraping process."""
    overall_found_urls = set()
    processed_page_count_total = 0

    for base_url in start_urls:
        logging.info(f"======== Starting source: {base_url} ========")
        current_source_urls = set()
        current_url = base_url
        page_count_for_source = 0

        while current_url and page_count_for_source < max_pages_per_source:
            logging.info(f"Fetching page: {current_url} (source: {base_url}, page {page_count_for_source + 1}/{max_pages_per_source})")
            html = fetch_page(current_url)
            if html is None:
                logging.warning(f"Failed to fetch content from {current_url}, stopping this source.")
                break

            new_urls = get_urls_from_html(html)
            if new_urls:
                logging.info(f"Found {len(new_urls)} new URLs on this page.")
                current_source_urls.update(new_urls)
                overall_found_urls.update(new_urls)
                logging.info(f"Current source URL count: {len(current_source_urls)}")
                logging.info(f"Total URL count across all sources: {len(overall_found_urls)}")

            next_page_url = get_next_page_url(html)
            current_url = next_page_url
            page_count_for_source += 1
            processed_page_count_total += 1
            time.sleep(random.uniform(20, 40))

        logging.info(f"======== Finished source: {base_url}, processed {page_count_for_source} pages ========")

    logging.info(f"\n======== All sources processed, total pages: {processed_page_count_total} ========")
    logging.info(f"Total unique URLs found: {len(overall_found_urls)}")

    if not overall_found_urls:
        logging.info("No URLs found for connectivity testing.")
    else:
        logging.info("Starting concurrent URL connectivity testing...")
        valid_urls = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(test_url_connectivity, overall_found_urls)
            for url, result in zip(overall_found_urls, results):
                if result:
                    valid_urls.append(url)

        logging.info(f"Connectivity testing complete. Valid URLs: {len(valid_urls)}")
        logging.info("Saving final valid URLs...")
        save_urls_to_file(valid_urls, 'data/jichang_subscribed_links.txt')
        logging.info("Final results saved.")

if __name__ == '__main__':
    start_urls_list = [
        'https://t.me/s/jichang_list',
       
    ]
    max_pages_to_crawl_per_source = 5
    concurrent_workers = 15

    if not os.path.exists('data'):
        os.makedirs('data')

    main(start_urls_list, max_pages_to_crawl_per_source, concurrent_workers)
