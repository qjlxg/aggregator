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

# 访问消息页面
driver.get("https://t.me/s/V2ray_Click")
time.sleep(5)  # 等待初始加载

# 滚动页面加载更多消息
for _ in range(5):  # 增加滚动次数以加载更多内容
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)  # 等待新消息加载

# 获取页面内容
page_content = driver.page_source

# 匹配目标链接
target_links = re.findall(
    r'(https?://[^\s"]+/api/v1/client/subscribe\?token=[a-zA-Z0-9_-]+)',
    page_content,
    re.IGNORECASE
)

# 检查是否抓到链接并保存
if target_links:
    with open('data/ji.txt', 'w') as f:
        for link in list(set(target_links)):  # 去重
            f.write(link + '\n')
    print(f"成功保存 {len(target_links)} 个链接到 data/ji.txt")
else:
    print("未找到符合条件的链接，请检查页面内容或正则表达式")

# 关闭浏览器
driver.quit()
