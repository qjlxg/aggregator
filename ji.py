# ji.txt generation script

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
    # Keep the t.me exclusion as we are scraping from t.me and don't want internal links
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    parsed = urlparse(url)
    # Require scheme and network location
    if not parsed.scheme or not parsed.netloc:
        return False
    # Only http/https schemes
    if parsed.scheme not in ('http', 'https'):
        return False
    # Check for valid hostname structure
    if not is_valid_hostname(parsed.netloc):
        return False
    # Exclude t.me links themselves
    if any(url.startswith(prefix) for prefix in invalid_prefixes):
        # Allow the base t.me page itself, but not internal links starting with t.me
        # However, for our specific token pattern search, we mainly expect external links.
        # The main fetcher starts with t.me/s/... which is handled.
        # This check primarily prevents extracting links *within* t.me that aren't full URLs.
        # Let's refine this: if the netloc IS 't.me', it's likely an internal link we don't want for tokens.
        if parsed.netloc == 't.me':
             return False
    return True

def clean_url(url):
    """Remove trailing punctuation from the URL."""
    while url and url[-1] in '.,;:!?)':
        url = url[:-1]
    return url

def get_specific_urls_from_html(html):
    """Extract and clean URLs containing specific token patterns from HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
        # Consider adding message meta for potential links? Let's stick to content for now.
    ])

    urls = set()
    # Define the patterns we are looking for
    token_patterns = ['/api/v1/client/subscribe?token=', 'subscribe?token=']

    for target in targets:
        # Extract from <a> tags
        for a_tag in target.find_all('a', href=True):
            href = clean_url(a_tag['href'].rstrip('/'))
            # Check if it's a valid URL structure AND contains one of the token patterns
            if is_valid_url(href) and any(pattern in href for pattern in token_patterns):
                urls.add(href)
            else:
                logging.debug(f"Discarded (pattern/validity mismatch) URL from <a> tag: {href}")

        # Extract from text content
        # Use a broader regex first, then filter by patterns and validity
        text = target.get_text(separator=' ', strip=True)
        # This regex finds http/https or www. followed by non-whitespace/quotes/angle brackets
        found_potential_urls = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text)
        for url_in_text in found_potential_urls:
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text
            url_in_text = clean_url(url_in_text.rstrip('/'))
            # Check if it's a valid URL structure AND contains one of the token patterns
            if is_valid_url(url_in_text) and any(pattern in url_in_text for pattern in token_patterns):
                 urls.add(url_in_text)
            else:
                 logging.debug(f"Discarded (pattern/validity mismatch) URL from text: {url_in_text}")

    return list(urls)

def test_url_connectivity(url, timeout=10):
    """Test if the URL is connectable by attempting a HEAD request."""
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        # Use a HEAD request as it's faster and we only need the status code
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        # Check for successful status codes (200 range)
        return 200 <= response.status_code < 300
    except requests.exceptions.RequestException as e:
        logging.debug(f"Connectivity test failed for {url}: {e}")
        return False

def get_next_page_url(html):
    """Extract the next page URL from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more and load_more.has_attr('href'):
        # Telegram relative paths need to be joined with the base domain
        return 'https://t.me' + load_more['href']
    return None

def fetch_page(url, timeout=15, max_retries=3):
    """Fetch page content with retries and random User-Agent."""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch {url} on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                # Wait longer on subsequent retries
                time.sleep(random.uniform(5, 12 + attempt * 5))
            else:
                logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None
    return None # Should not be reached if max_retries > 0

def save_urls_to_file(urls, filename='ji.txt'):
    """Save URLs to a file."""
    # Ensure the directory exists (though 'ji.txt' is in root, good practice)
    output_dir = os.path.dirname(filename)
    if output_dir and not os.path.exists(output_dir):
         os.makedirs(output_dir)

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in sorted(list(urls)): # Sort for consistency
                f.write(url + '\n')
        logging.info(f"Valid URLs saved to {filename} (count: {len(urls)})")
    except IOError as e:
        logging.error(f"Failed to save URLs to {filename}: {e}")

def main(start_urls, max_pages_per_source=90, max_workers=10):
    """Main function to control the scraping and testing process for specific token URLs."""
    overall_found_specific_urls = set()
    processed_page_count_total = 0

    for base_url in start_urls:
        logging.info(f"======== Starting source: {base_url} ========")
        current_source_specific_urls = set()
        current_url = base_url
        page_count_for_source = 0

        while current_url and page_count_for_source < max_pages_per_source:
            logging.info(f"Fetching page: {current_url} (source: {base_url}, page {page_count_for_source + 1}/{max_pages_per_source})")
            html = fetch_page(current_url)
            if html is None:
                logging.warning(f"Failed to fetch content from {current_url}, stopping this source.")
                break # Stop processing this source if a page fails to fetch

            # Use the modified function to get only specific token URLs
            new_specific_urls = get_specific_urls_from_html(html)

            if new_specific_urls:
                logging.info(f"Found {len(new_specific_urls)} new specific URLs on this page.")
                current_source_specific_urls.update(new_specific_urls)
                overall_found_specific_urls.update(new_specific_urls)
                logging.info(f"Current source specific URL count: {len(current_source_specific_urls)}")
                logging.info(f"Total specific URL count across all sources: {len(overall_found_specific_urls)}")
            else:
                 logging.info("No new specific URLs found on this page.")

            next_page_url = get_next_page_url(html)

            # Decide whether to continue to the next page
            if next_page_url:
                current_url = next_page_url
                page_count_for_source += 1
                processed_page_count_total += 1
                # Add a delay between page fetches to be polite
                time.sleep(random.uniform(15, 30)) # Increased delay slightly
            else:
                logging.info(f"No more pages found for source: {base_url}")
                current_url = None # Stop the loop for this source

        logging.info(f"======== Finished source: {base_url}, processed {page_count_for_source} pages ========")

    logging.info(f"\n======== All sources processed, total pages: {processed_page_count_total} ========")
    logging.info(f"Total unique specific URLs found before testing: {len(overall_found_specific_urls)}")

    if not overall_found_specific_urls:
        logging.info("No specific URLs found for connectivity testing.")
        # Save an empty file or indicate no URLs found
        save_urls_to_file([], 'ji.txt')
    else:
        logging.info("Starting concurrent URL connectivity testing for specific URLs...")
        valid_specific_urls = []
        # Use ThreadPoolExecutor for concurrent testing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Map the connectivity test function to each URL
            # executor.map returns results in the order the inputs were given
            future_to_url = {executor.submit(test_url_connectivity, url): url for url in overall_found_specific_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    is_connectable = future.result()
                    if is_connectable:
                        valid_specific_urls.append(url)
                        # logging.debug(f"URL {url} is connectable.") # Too verbose
                    else:
                        logging.debug(f"URL {url} is not connectable.")
                except Exception as exc:
                    logging.error(f"URL {url} generated an exception during testing: {exc}")

        logging.info(f"Connectivity testing complete. Valid specific URLs found: {len(valid_specific_urls)}")
        logging.info("Saving final valid specific URLs to ji.txt...")
        save_urls_to_file(valid_specific_urls, 'ji.txt')
        logging.info("Final results saved to ji.txt.")


if __name__ == '__main__':
    # List of Telegram channel archive URLs to scrape
    start_urls_list = [
        'https://t.me/s/vpn_3000',
        'https://t.me/s/ccbaohe',
        'https://t.me/s/wangcai_8',
        # Add other source URLs here if needed
    ]

    # Maximum number of pages to crawl per source URL
    # 90 pages was in the original; keeping it but making it adjustable
    max_pages_to_crawl_per_source = 15

    # Number of worker threads for concurrent connectivity testing
    concurrent_workers = 20 # Increased from 15 for potentially faster testing

    # Import concurrent.futures within the __main__ block or globally if needed elsewhere
    import concurrent.futures

    main(start_urls_list, max_pages_to_crawl_per_source, concurrent_workers)
