import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# 设置 Chrome 的 headless 模式选项
options = Options()
options.add_argument("--headless")  # 无界面运行
options.add_argument("--no-sandbox")  # 兼容 GitHub Actions 环境
options.add_argument("--disable-dev-shm-usage")  # 避免共享内存问题

# 初始化 WebDriver
driver = webdriver.Chrome(options=options)

# 导航到 Telegram 页面（替换为实际的目标 URL）
driver.get("https://t.me/V2ray_Click")  # 请替换为您的目标 Telegram 频道或群组 URL
driver.implicitly_wait(10)  # 等待页面加载，视情况调整时间

# 定义提取链接的函数
def extract_links(driver):
    # 获取页面源代码并用 BeautifulSoup 解析
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    # 查找所有带有 href 属性的 <a> 标签
    links = soup.find_all('a', href=True)
    # 使用正则表达式过滤包含 'api/v1/client/subscribe?token=' 的链接
    subscribe_links = [link['href'] for link in links if re.search(r'api/v1/client/subscribe\?token=', link['href'])]
    return subscribe_links

# 提取符合条件的链接
subscribe_links = extract_links(driver)

# 将结果保存到文件
with open('data/ji.txt', 'w') as f:
    for link in subscribe_links:
        f.write(link + '\n')

# 关闭浏览器
driver.quit()
