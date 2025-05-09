import requests
import os
import schedule
import time
from datetime import datetime
from bs4 import BeautifulSoup

# 定义要爬取的网站和对应的图片链接提取函数
def get_bing_image_url():
    """从 Bing 获取每日图片 URL"""
    url = "https://www.bing.com"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    img_url = soup.find('link', {'id': 'preloadBg'})['href']
    return url + img_url

def get_nasa_apod_image_url():
    """从 NASA APOD 获取每日图片 URL"""
    url = "https://apod.nasa.gov/apod/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'):
        img_url = img_tag['src']
        if not img_url.startswith('http'):
            img_url = url + img_url
        return img_url
    return None

# 你可以添加更多的网站和对应的函数
websites = {
    "bing": get_bing_image_url,
    "nasa_apod": get_nasa_apod_image_url,
}

def download_image(image_url, filepath):
    """下载图片到指定路径"""
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()  # 检查请求是否成功

        with open(filepath, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        print(f"图片已保存到: {filepath}")

    except requests.exceptions.RequestException as e:
        print(f"下载失败: {e}")
    except Exception as e:
        print(f"保存文件时出错: {e}")

def job():
    """每日任务：下载所有网站的图片"""
    today = datetime.now()
    year = today.year
    month = today.month
    day = today.day

    for website_name, get_image_url_func in websites.items():
        try:
            image_url = get_image_url_func()

            if image_url:
                 # 创建目录，如果不存在
                dir_path = os.path.join("data", website_name, str(year), str(month).zfill(2))
                os.makedirs(dir_path, exist_ok=True)

                filepath = os.path.join(dir_path, f"{day}.jpg")  #  可以根据实际情况更改扩展名
                download_image(image_url, filepath)
            else:
                print(f"无法从 {website_name} 获取图片 URL。")
        except Exception as e:
               print(f"处理 {website_name} 时发生错误： {e}")

# 每天的特定时间运行任务
schedule.every().day.at("08:00").do(job)  #  修改为你希望运行的时间

while True:
    schedule.run_pending()
    time.sleep(60) # 每分钟检查一次
