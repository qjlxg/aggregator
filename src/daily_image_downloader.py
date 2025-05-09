# src/daily_image_downloader.py

import requests
import os
from datetime import datetime
from bs4 import BeautifulSoup

# 直接在脚本中定义配置
config = {
    'websites': {
        'bing': {
            'enabled': True,
            'url_function': "get_bing_image_url"
        },
        'nasa_apod': {
            'enabled': True,
            'url_function': "get_nasa_apod_image_url"
        }
    }
}

def get_bing_image_url():
    """从 Bing 获取每日图片 URL"""
    url = "https://www.bing.com"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        img_url = soup.find('link', {'id': 'preloadBg'})['href']
        return url + img_url
    except Exception as e:
        print(f"获取 Bing 图片 URL 失败: {e}")
        return None

def get_nasa_apod_image_url():
    """从 NASA APOD 获取每日图片 URL"""
    url = "https://apod.nasa.gov/apod/"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            if not img_url.startswith('http'):
                img_url = 'https://apod.nasa.gov/apod/' + img_url
            return img_url
        return None
    except Exception as e:
        print(f"获取 NASA APOD 图片 URL 失败: {e}")
        return None

def download_image(image_url, filepath):
    """下载图片到指定路径"""
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()

        with open(filepath, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        print(f"图片已保存到: {filepath}")
    except Exception as e:
        print(f"下载或保存图片失败: {e}")

def main():
    today = datetime.now()
    year = today.year
    month = today.month
    day = today.day

    for website_name, website_config in config['websites'].items():
        if website_config.get('enabled', True):
            try:
                url_function_name = website_config.get('url_function')
                url_function = globals().get(url_function_name)

                if not url_function:
                    print(f"找不到函数: {url_function_name}")
                    continue

                image_url = url_function()
                if image_url:
                    dir_path = os.path.join(os.path.dirname(__file__), website_name)
                    os.makedirs(dir_path, exist_ok=True)

                    filename = f"{website_name}{year}{str(month).zfill(2)}{str(day).zfill(2)}.jpg"
                    filepath = os.path.join(dir_path, filename)
                    download_image(image_url, filepath)
                else:
                    print(f"无法从 {website_name} 获取图片 URL。")
            except Exception as e:
                print(f"处理 {website_name} 时发生错误： {e}")

if __name__ == "__main__":
    main()
