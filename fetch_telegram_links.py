from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import re

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
driver = webdriver.Chrome(options=options)

# 导航到消息页面
driver.get("https://t.me/s/V2ray_Click")
time.sleep(5)  # 初始加载

# 滚动加载更多消息
for _ in range(5):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

# 正则匹配目标链接
page_content = driver.page_source
target_links = re.findall(
    r'(https?://[^\s"]+/api/v1/client/subscribe\?token=[a-zA-Z0-9_-]+)',
    page_content,
    re.IGNORECASE
)

# 去重保存
with open('data/ji.txt', 'w') as f:
    for link in list(set(target_links)):
        f.write(link + '\n')

driver.quit()
