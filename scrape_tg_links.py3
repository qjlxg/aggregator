import requests
import threading
import json
import os
import time
import random
import re
from bs4 import BeautifulSoup
from datetime import datetime

# 禁用 SSL 警告并设置 requests 请求
requests.get = lambda url, **kwargs: requests.request(
    method="GET", url=url, verify=False, **kwargs
)
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 清屏
os.system('cls' if os.name == 'nt' else 'clear')

# 定义加载 JSON 文件的函数
def json_load(path):
    with open(path, 'r', encoding="utf-8") as file:
        list_content = json.load(file)
    return list_content

# 从 telegram channels.json 加载频道名称
tg_name_json = json_load('telegram channels.json')

# 获取用户输入
thrd_pars = int(input('\nThreads for parsing: '))
pars_dp = int(input('\nParsing depth (1dp = 20 last tg posts): '))

print(f'\nTotal channel names in telegram channels.json - {len(tg_name_json)}')

# 记录开始时间
start_time = datetime.now()

# 设置线程信号量
sem_pars = threading.Semaphore(thrd_pars)

# 用于存储提取的链接
links = []

print(f'\nStart Parsing...\n')

# 定义处理频道的函数，只提取链接
def process(i_url):
    sem_pars.acquire()
    html_pages = []   
    cur_url = i_url
    for itter in range(1, pars_dp + 1):
        while True:
            try:
                response = requests.get(f'https://t.me/s/{cur_url}')
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
        # 提取所有 <a> 标签中的 href 属性
        a_tags = soup.find_all('a')
        for tag in a_tags:
            href = tag.get('href')
            if href:  # 确保 href 不为空
                links.append(href)
    sem_pars.release()

# 启动多线程处理每个频道
for url in tg_name_json:
    threading.Thread(target=process, args=(url,)).start()

# 等待所有线程完成
while threading.active_count() > 1:
    time.sleep(1)

print(f'\nParsing completed - {str(datetime.now() - start_time).split(".")[0]}')

# 保存提取的链接到文件
print(f'\nSaving extracted links...')
with open("extracted_links.txt", "w", encoding="utf-8") as file:
    for link in links:
        file.write(link + "\n")

print(f'\nTime spent - {str(datetime.now() - start_time).split(".")[0]}')
input('\nPress Enter to finish ...')
