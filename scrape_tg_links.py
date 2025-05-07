import requests
import threading
import json
import os
import time
import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

# Disable SSL warnings and set up requests
requests.get = lambda url, **kwargs: requests.request(
    method="GET", url=url, verify=False, **kwargs
)
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# Clear screen (optional; harmless if TERM is unset)
os.system('cls' if os.name == 'nt' else 'clear')

# Load JSON file with channel names
def json_load(path):
    with open(path, 'r', encoding="utf-8") as file:
        return json.load(file)

# Load Telegram channel names
tg_name_json = json_load('telegram channels.json')

# Get user inputs
thrd_pars = int(input('\nThreads for parsing: '))
pars_dp = int(input('\nParsing depth (1dp = 20 last tg posts): '))

print(f'\nTotal channel names in telegram channels.json - {len(tg_name_json)}')

# Record start time
start_time = datetime.now()

# Set up threading semaphore
sem_pars = threading.Semaphore(thrd_pars)

# List to store extracted links
links = []
links_lock = threading.Lock()  # Ensure thread-safe appending

print(f'\nStart Parsing...\n')

# Process each channel and extract links
def process(i_url):
    sem_pars.acquire()
    html_pages = []
    cur_url = i_url
    for itter in range(1, pars_dp + 1):
        while True:
            try:
                response = requests.get(f'https://t.me/s/{cur_url}')
                base_url = response.url  # Use final URL after redirects
            except:
                time.sleep(random.randint(5, 25))
                continue
            else:
                if itter == pars_dp:
                    print(f'{tg_name_json.index(i_url) + 1} of {len(tg_name_json)} - {i_url}')
                html_pages.append(response.text)
                last_datbef = re.findall(r'(?:data-before=")(\d*)', response.text)
                break
        if not last_datbef:
            break
        cur_url = f'{i_url}?before={last_datbef[0]}'
    for page in html_pages:
        soup = BeautifulSoup(page, 'html.parser')
        # Extract links from message text only
        message_texts = soup.find_all(class_='tgme_widget_message_text')
        for message_text in message_texts:
            a_tags = message_text.find_all('a')
            for tag in a_tags:
                href = tag.get('href')
                if href:
                    # Convert to absolute URL
                    absolute_url = urljoin(base_url, href)
                    # Filter for http:// or https://
                    if absolute_url.startswith(('http://', 'https://')):
                        with links_lock:
                            links.append(absolute_url)
    sem_pars.release()

# Start threads for each channel
for url in tg_name_json:
    threading.Thread(target=process, args=(url,)).start()

# Wait for all threads to complete
while threading.active_count() > 1:
    time.sleep(1)

print(f'\nParsing completed - {str(datetime.now() - start_time).split(".")[0]}')

# Remove duplicates and save links
unique_links = sorted(list(set(links)))
print(f'\nSaving {len(unique_links)} unique extracted links...')
with open("extracted_links.txt", "w", encoding="utf-8") as file:
    for link in unique_links:
        file.write(link + "\n")

print(f'\nTime spent - {str(datetime.now() - start_time).split(".")[0]}')
input('\nPress Enter to finish ...')
