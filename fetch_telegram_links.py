from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import re

# 配置 Chrome 选项
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# 初始化 WebDriver
driver = webdriver.Chrome(options=options)

# 目标频道列表
channel_urls = [
    "https://t.me/s/vpn_3000",
    "https://t.me/s/V2ray_Click",
    "https://t.me/s/academi_vpn",
    "https://t.me/s/dingyue_center",
    "https://t.me/s/freedatazone1",
    "https://t.me/s/freev2rayi",
    "https://t.me/s/mypremium98",
    "https://t.me/s/inikotesla",
    "https://t.me/s/v2rayngalpha"
]

all_links = []

# 遍历频道
for url in channel_urls:
    print(f"正在抓取频道: {url}")
    driver.get(url)
    time.sleep(5)  # 等待页面加载

    # 滚动加载更多消息
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    # 提取链接
    page_content = driver.page_source
    target_links = re.findall(
        r'(https?://[^\s"]+/api/v1/client/subscribe\?token=[a-zA-Z0-9_-]+)',
        page_content,
        re.IGNORECASE
    )
    all_links.extend(target_links)
    print(f"从 {url} 抓取到 {len(target_links)} 个链接")

# 去重并保存
unique_links = list(set(all_links))
if unique_links:
    with open('data/ji.txt', 'w') as f:
        for link in unique_links:
            f.write(link + '\n')
    print(f"成功保存 {len(unique_links)} 个唯一链接到 data/ji.txt")
else:
    print("未找到任何符合条件的链接")

driver.quit()
