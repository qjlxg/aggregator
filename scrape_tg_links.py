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

# 禁用 SSL 警告并配置 requests
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
requests.get = lambda url, **kwargs: requests.request(
    method="GET", url=url, verify=False, **kwargs
)

# 加载 JSON 文件
def json_load(path):
    with open(path, 'r', encoding="utf-8") as file:
        return json.load(file)

# 读取 Telegram 频道名称
tg_name_json = json_load('telegram_channels.json')

# 从环境变量获取线程数和解析深度，设置默认值
thrd_pars = int(os.environ.get('THREADS', 5))
pars_dp = int(os.environ.get('DEPTH', 2))

print(f'\nTotal channel names in telegram_channels.json - {len(tg_name_json)}')

# 记录开始时间
start_time = datetime.now()

# 设置线程信号量
sem_pars = threading.Semaphore(thrd_pars)

# 存储提取的链接
links = set()
links_lock = threading.Lock()  # 线程安全锁

print(f'\nStart Parsing...\n')

# 处理单个频道并提取链接
def process(i_url):
    sem_pars.acquire()
    html_pages = []
    cur_url = i_url
    for itter in range(1, pars_dp + 1):
        while True:
            try:
                response = requests.get(f'https://t.me/s/{cur_url}')
                base_url = response.url  # 使用最终的重定向 URL
            except Exception as e:
                print(f"Failed to fetch page for {i_url}: {e}")
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
        # 仅从消息内容提取链接
        message_texts = soup.find_all(class_='tgme_widget_message_text')
        for message_text in message_texts:
            a_tags = message_text.find_all('a')
            for tag in a_tags:
                href = tag.get('href')
                if href:
                    # 转换为绝对 URL
                    absolute_url = urljoin(base_url, href)
                    # 筛选以 http:// 或 https:// 开头的链接
                    if absolute_url.startswith(('http://', 'https://')):
                        with links_lock:
                            links.add(absolute_url)
    sem_pars.release()

# 为每个频道启动线程
for url in tg_name_json:
    threading.Thread(target=process, args=(url,)).start()

# 等待所有线程完成
while threading.active_count() > 1:
    time.sleep(1)

print(f'\nParsing completed - {str(datetime.now() - start_time).split(".")[0]}')

# 保存唯一链接
unique_links = sorted(list(links))
print(f'\nSaving {len(unique_links)} unique extracted links...')
with open("extracted_links.txt", "w", encoding="utf-8") as file:
    for link in unique_links:
        file.write(link + "\n")

print(f'\nTime spent - {str(datetime.now() - start_time).split(".")[0]}')
