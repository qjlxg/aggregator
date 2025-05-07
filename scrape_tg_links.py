# scrape_tg_links.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import os

channel_url = os.environ.get("TELEGRAM_CHANNEL_URL", "https://t.me/s/dingyue_center")
output_file = os.path.join("data", "ji2.txt")  # 使用相对路径和 os.path.join
data_dir = "data"

# 确保 data 目录存在
if not os.path.exists(data_dir):
    os.makedirs(data_dir)


def scrape_links():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    # 添加以下参数来解决一些 Chrome 在无头模式下可能遇到的问题
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # 注意: Chrome WebDriver 必须已安装, 且版本与 Chrome 浏览器匹配
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(channel_url)
        time.sleep(5)

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        message_elements = soup.find_all('div', class_='tgme_widget_message_text')

        with open(output_file, 'w', encoding='utf-8') as f:
            for message_element in message_elements:
                links = message_element.find_all('a')
                for link in links:
                    url = link['href']
                    f.write(url + '\n')

        print(f"Urls saved to {output_file}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        driver.quit()


if __name__ == "__main__":
    scrape_links()
