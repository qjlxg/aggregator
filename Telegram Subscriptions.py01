import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
import threading
from queue import Queue
from github import Github
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


search_keywords_env_str = os.environ.get('SEARCH_KEYWORDS_ENV')
if search_keywords_env_str:
    SEARCH_KEYWORDS = [kw.strip() for kw in search_keywords_env_str.split(',') if kw.strip()]
    if not SEARCH_KEYWORDS:
        logging.error("Environment variable 'SEARCH_KEYWORDS_ENV' is set but contains no valid keywords after parsing. Exiting.")
        sys.exit(1)
else:
    logging.error("Environment variable 'SEARCH_KEYWORDS_ENV' is NOT set. Cannot proceed without search keywords. Exiting.")
    sys.exit(1)


SUBSCRIPTION_TARGET_REPO = os.environ.get('SUBSCRIPTION_TARGET_REPO')
SUBSCRIPTION_SAVE_PATH = os.environ.get('SUBSCRIPTION_SAVE_PATH')
if not SUBSCRIPTION_TARGET_REPO or not SUBSCRIPTION_SAVE_PATH:
    logging.error("Environment variables 'SUBSCRIPTION_TARGET_REPO' or 'SUBSCRIPTION_SAVE_PATH' are NOT set. Exiting.")
    sys.exit(1)


CONFIG_REPO_NAME = os.environ.get('CONFIG_REPO_NAME')
CONFIG_FILE_PATH = os.environ.get('CONFIG_FILE_PATH')
if not CONFIG_REPO_NAME or not CONFIG_FILE_PATH:
    logging.error("Environment variables 'CONFIG_REPO_NAME' or 'CONFIG_FILE_PATH' are NOT set. Exiting.")
    sys.exit(1)


GT_TOKEN = os.environ.get('GT_TOKEN')
if not GT_TOKEN:
    logging.error("Environment variable 'GT_TOKEN' is NOT set. Cannot proceed. Exiting.")
    sys.exit(1)


MAX_PAGES_TO_CRAWL = 1
NUM_WORKING_THREADS = 5

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36',
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    'Mozilla/5.0 (compatible; DuckDuckBot/1.0; libcurl/7.64.1)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave/92.1.27.111 Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Brave/92.1.27.111 Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.105 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 9; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 7.0; SM-G935F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.83 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 11; Redmi Note 10 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1',
]

def get_random_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}

def is_valid_url(url):
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text', 'tgme_widget_message_photo',
        'tgme_widget_message_video', 'tgme_widget_message_document',
        'tgme_widget_message_poll'
    ])
    excluded_domains = (
        "aliyundrive.com", ".top", "website", "pan.baidu.com", "raw.bgithub.xyz",
        "t.me", "yam", "play.google.com", "app", "777.hz.cz", "releases",
        "org", "html", "apk", "appleID", "apps.apple.com", "fs.v2rayse.com"
    )
    urls = set()
    for target in targets:
        text = target.get_text(separator=' ', strip=True)
        found_urls = re.findall(r'(?:https?://|www\.)[^\s]+', text)
        
        valid_urls = [
            url for url in found_urls
            if any(keyword in url for keyword in SEARCH_KEYWORDS)
            and not any(domain in url for domain in excluded_domains)
        ]
        urls.update(valid_urls)
    return list(urls)

def test_url_connectivity(url, timeout=5):
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.warning(f"URL {url} connectivity test failed: {e}")
        return False

def get_next_page_url(html):
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more:
        next_page_url = 'https://t.me' + load_more['href']
        logging.info(f"Found next page URL: {next_page_url}")
        return next_page_url
    else:
        logging.info("No next page URL found")
        return None

def fetch_page(url, headers, timeout=10, max_retries=3):
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            end_time = time.time()
            logging.info(f"Successfully fetched {url} (Attempt {attempt + 1}/{max_retries}), took: {end_time - start_time:.2f}s")
            return response.text
        except requests.RequestException as e:
            logging.warning(f"Failed to fetch {url} on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                sleep_time = random.uniform(38, 53)
                logging.info(f"Waiting {sleep_time:.2f} seconds before retrying")
                time.sleep(sleep_time)
            else:
                logging.error(f"Failed to fetch {url}, exceeded max retries: {e}")
                return None

def save_urls_to_github(repo_name, file_path, content, github_token):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents(file_path)
            updated_content = contents.decoded_content.decode('utf-8') + '\n' + '\n'.join(content)
            repo.update_file(contents.path, "Add new subscriptions", updated_content.encode('utf-8'), contents.sha)
            logging.info(f"URLs appended to GitHub: {repo_name}/{file_path}")
            return True
        except Exception as e:
            if "Not Found" in str(e):
                repo.create_file(file_path, "Initial subscriptions", '\n'.join(content).encode('utf-8'))
                logging.info(f"URLs initially saved to GitHub: {repo_name}/{file_path}")
                return True
            else:
                logging.error(f"Failed to save to GitHub: {e}")
                return False
    except Exception as e:
        logging.error(f"GitHub API authentication or repository access failed: {e}")
        return False

def crawl_single_source(start_url, headers, max_pages, url_queue):
    current_url = start_url
    page_count = 0
    while current_url and page_count < max_pages:
        logging.info(f"Crawling: {current_url} (Page {page_count + 1}/{max_pages}, Source: {start_url})")
        html = fetch_page(current_url, headers)
        if html is None:
            logging.warning(f"Could not get HTML for {current_url}, stopping crawl from this source")
            break
        new_urls = get_urls_from_html(html)
        logging.info(f"Extracted {len(new_urls)} URLs from {current_url}")
        for url in new_urls:
            url_queue.put(url)
        current_url = get_next_page_url(html)
        page_count += 1
        sleep_time = random.uniform(35, 45)
        logging.info(f"Waiting {sleep_time:.2f} seconds before crawling next page")
        time.sleep(sleep_time)

def worker(url_queue, valid_urls, lock):
    while True:
        url = url_queue.get()
        if url is None:
            logging.info("Worker received stop signal, exiting")
            break
        try:
            if test_url_connectivity(url):
                with lock:
                    valid_urls.add(url)
                logging.info(f"URL {url} is valid, added to valid URL set")
            else:
                logging.warning(f"URL {url} connectivity test failed")
        except Exception as e:
            logging.error(f"Error testing connectivity for URL {url}: {e}")
        finally:
            url_queue.task_done()

def main(start_urls):
   
    global SUBSCRIPTION_TARGET_REPO, SUBSCRIPTION_SAVE_PATH, GT_TOKEN

    logging.info(f"Attempting to save to GitHub repo: {SUBSCRIPTION_TARGET_REPO}, path: {SUBSCRIPTION_SAVE_PATH}")
    
  
    try:
        g = Github(GT_TOKEN)
        user = g.get_user()
        logging.info(f"GitHub Username: {user.login}")
    except Exception as e:
        logging.error(f"GitHub API authentication failed with provided token: {e}. Saving to GitHub will be skipped.")
       
        sys.exit(1) 

    url_queue = Queue()
    valid_urls = set()
    lock = threading.Lock()

    threads = []
    for _ in range(NUM_WORKING_THREADS):
        t = threading.Thread(target=worker, args=(url_queue, valid_urls, lock))
        t.daemon = True
        t.start()
        threads.append(t)

    crawler_threads = []
    for start_url in start_urls:
        headers = get_random_headers()
        t = threading.Thread(target=crawl_single_source, args=(start_url, headers, MAX_PAGES_TO_CRAWL, url_queue))
        t.daemon = True
        t.start()
        crawler_threads.append(t)

    for t in crawler_threads:
        t.join()

    url_queue.join()

    logging.info("All source crawling tasks completed. Sending stop signals to workers.")

    for _ in range(NUM_WORKING_THREADS):
        url_queue.put(None)
    for t in threads:
        t.join()

    logging.info("All worker threads exited.")
    logging.info(f"Number of valid URLs: {len(valid_urls)}")

    
    if save_urls_to_github(SUBSCRIPTION_TARGET_REPO, SUBSCRIPTION_SAVE_PATH, list(valid_urls), GT_TOKEN):
        logging.info("Successfully saved URLs to GitHub.")
    else:
        logging.error("Failed to save URLs to GitHub.")

if __name__ == '__main__':
   
    start_urls_list = []

    try:
        g = Github(GT_TOKEN) 
        repo = g.get_repo(CONFIG_REPO_NAME) 
        config_content_file = repo.get_contents(CONFIG_FILE_PATH) 
        config_content = config_content_file.decoded_content.decode('utf-8')
        start_urls_list = [url.strip() for url in config_content.strip().split('\n') if url.strip()]
        logging.info(f"Read {len(start_urls_list)} starting URLs from GitHub.")
    except Exception as e:
        logging.error(f"Failed to read configuration file from GitHub ({CONFIG_REPO_NAME}/{CONFIG_FILE_PATH}): {e}. Exiting.")
        sys.exit(1) # 如果无法读取配置，直接退出

    main(start_urls_list)
