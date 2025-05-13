import requests
from bs4 import BeautifulSoup
import re
import time
import random
import logging
import os
from concurrent.futures import ThreadPoolExecutor

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User-Agent 池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
]

def is_valid_url(url):
    """判断URL是否有效 (非Telegram链接)"""
    invalid_prefixes = ('https://t.me', 'http://t.me', 't.me')
    # 简单的URL格式校验
    if not re.match(r'^https?://', url):
        return False
    return not any(url.startswith(prefix) for prefix in invalid_prefixes)

def get_urls_from_html(html):
    """从HTML中提取 URLs"""
    soup = BeautifulSoup(html, 'html.parser')
    targets = soup.find_all(class_=[
        'tgme_widget_message_text',
        'tgme_widget_message_photo',
        'tgme_widget_message_video',
        'tgme_widget_message_document',
        'tgme_widget_message_poll',
    ])

    urls = set()

    for target in targets:
        # 尝试从 <a> 标签的 href 属性直接提取
        for a_tag in target.find_all('a', href=True):
            href = a_tag['href']
            if is_valid_url(href):
                urls.add(href)

        # 也从文本内容中提取，以捕获没有被 <a> 标签包裹的链接
        text = target.get_text(separator=' ', strip=True)
        found_urls_in_text = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+', text) # 更精确的正则
        for url_in_text in found_urls_in_text:
            # 确保提取到的 www. 开头的链接被补全协议头
            if url_in_text.startswith('www.'):
                url_in_text = 'http://' + url_in_text # 默认为http, test_url_connectivity会处理https重定向
            if is_valid_url(url_in_text):
                urls.add(url_in_text)
    return list(urls)


def test_url_connectivity(url, timeout=10):
    """测试 URL 是否可连通 (增加超时和User-Agent)"""
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        # 允许重定向，并且使用stream=True来避免下载整个内容，只获取头部信息
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        # 检查最终URL的状态码
        if response.status_code == 200:
            # 可选：进一步检查 content-type，避免下载非预期文件
            # content_type = response.headers.get('Content-Type', '')
            # if 'text/html' in content_type or 'application/json' in content_type or not content_type: # 示例
            return True
        # logging.warning(f"URL {url} 连接测试最终状态码: {response.status_code}")
        return False
    except requests.RequestException as e:
        # logging.warning(f"URL {url} 连接测试失败: {e}")
        return False


def get_next_page_url(html):
    """从HTML中提取下一页的URL"""
    soup = BeautifulSoup(html, 'html.parser')
    load_more = soup.find('a', class_='tme_messages_more')
    if load_more and load_more.has_attr('href'):
        next_page_url = 'https://t.me' + load_more['href']
        return next_page_url
    return None


def fetch_page(url, timeout=15, max_retries=3):
    """抓取页面内容，带有重试机制和随机User-Agent"""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(f"抓取页面 {url} 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 12 + attempt * 2)) # 增加重试等待时间
            else:
                logging.error(f"抓取页面 {url} 失败，超出最大重试次数")
                return None
    return None

def save_urls_to_file(urls, filename='data/jichang_list.txt'):
    """保存 URL 到文件"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    try:
        # logging.info(f"尝试保存 URL 到文件: {filename}, 数量: {len(urls)}")
        with open(filename, 'w', encoding='utf-8') as f:
            for url in sorted(list(urls)): # 保存前排序
                f.write(url + '\n')
        logging.info(f"URL 已成功保存到 {filename} (数量: {len(urls)})")
    except IOError as e:
        logging.error(f"保存 URL 到文件 {filename} 失败: {e}")
        logging.error(f"错误详情: {str(e)}")


def main(start_urls, max_pages_per_source=90, max_workers=10):
    """主函数，控制抓取流程，支持多个起始URL"""
    overall_found_urls = set() # 存储从所有来源找到的URL
    processed_page_count_total = 0

    for base_url in start_urls:
        logging.info(f"======== 开始处理来源: {base_url} ========")
        current_source_urls = set()
        current_url = base_url
        page_count_for_source = 0

        while current_url and page_count_for_source < max_pages_per_source:
            logging.info(f"正在抓取页面: {current_url} (来源: {base_url}, 第 {page_count_for_source + 1}/{max_pages_per_source} 页)")

            html = fetch_page(current_url)
            if html is None:
                logging.warning(f"抓取页面内容失败 {current_url}，停止抓取此来源。")
                break

            new_urls = get_urls_from_html(html)
            if new_urls:
                logging.info(f"从当前页面找到 {len(new_urls)} 个新 URL。")
                current_source_urls.update(new_urls)
                overall_found_urls.update(new_urls) # 添加到总的URL集合
                logging.info(f"当前来源累计 URL 数量: {len(current_source_urls)}")
                logging.info(f"所有来源累计 URL 总数: {len(overall_found_urls)}")

            next_page_url = get_next_page_url(html)
            current_url = next_page_url
            # logging.info(f"下一页 URL: {current_url}") # 日志有点多，可以注释掉

            page_count_for_source += 1
            processed_page_count_total +=1
            time.sleep(random.uniform(20, 40)) # 降低请求频率

            # 保存中间结果 (可选，如果希望每个来源都保存或总的中间结果)
            # logging.info("保存中间结果...")
            # save_urls_to_file(list(overall_found_urls), 'data/ji_partial.txt')
            # logging.info("中间结果保存完毕。")
        logging.info(f"======== 来源: {base_url} 处理完毕，共抓取 {page_count_for_source} 页 ========")


    logging.info(f"\n======== 所有来源抓取完毕，总共处理 {processed_page_count_total} 个页面 ========")
    logging.info(f"找到的原始 URL 总数 (去重后): {len(overall_found_urls)}")

    # 并发测试 URL 连通性
    if not overall_found_urls:
        logging.info("没有找到任何URL进行连通性测试。")
    else:
        logging.info("开始并发测试 URL 连通性...")
        valid_urls = []
        # 为了避免日志混乱，test_url_connectivity 中的详细日志已被注释
        # 可以使用 tqdm 库来显示进度条，如果URL数量很多的话
        # from tqdm import tqdm
        # with ThreadPoolExecutor(max_workers=max_workers) as executor:
        #    results = list(tqdm(executor.map(test_url_connectivity, overall_found_urls), total=len(overall_found_urls), desc="测试URL连通性"))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(test_url_connectivity, overall_found_urls)
            for url, result in zip(overall_found_urls, results):
                if result:
                    valid_urls.append(url)
                # else:
                #     logging.debug(f"URL 不可连接或无效: {url}") # 可以为调试开启

        logging.info(f"URL 连通性测试完成。有效 (可连接) 的 URL 数量: {len(valid_urls)}")

        # 保存最终结果
        logging.info("保存最终的有效URL...")
        save_urls_to_file(valid_urls, 'data/jichang_subscribed_links.txt') # 修改了最终文件名
        logging.info("最终结果保存完毕。")

if __name__ == '__main__':
    # 在这里定义你的起始URL列表
    start_urls_list = [
        #'https://t.me/s/jichang_list',
        
'https://t.me/s/vpn_3000',
'https://t.me/s/academi_vpn',
'https://t.me/s/dingyue_center',
'https://t.me/s/freedatazone1',
'https://t.me/s/freev2rayi',
'https://t.me/s/mypremium98',
'https://t.me/s/inikotesla',
'https://t.me/s/v2rayngalpha',
'https://t.me/s/v2rayngalphagamer',
'https://t.me/s/jiedian_share',
'https://t.me/s/vpn_mafia',
'https://t.me/s/dr_v2ray',
'https://t.me/s/allv2board',
'https://t.me/s/bigsmoke_config',
'https://t.me/s/vpn_443',
'https://t.me/s/prossh',
'https://t.me/s/mftizi',
'https://t.me/s/qun521',
'https://t.me/s/v2rayng_my2',
'https://t.me/s/go4sharing',
'https://t.me/s/trand_farsi',
'https://t.me/s/vpnplusee_free',
'https://t.me/s/freekankan',
'https://t.me/s/awxdy666',
'https://t.me/s/freeVPNjd',
'https://t.me/s/hkaa0',
'https://t.me/s/ccbaohe',
'https://t.me/s/MxlShare',
'https://t.me/hack_proxy',
'https://t.me/s/mrjdfx',
'https://t.me/s/QrV2ray',
'https://t.me/s/V2ray_v2ray_v2ray',

    ]
    max_pages_to_crawl_per_source = 5  # 每个来源URL最大抓取页数
    concurrent_workers = 15            # 测试连通性的并发线程数

    # 确保data目录存在
    if not os.path.exists('data'):
        os.makedirs('data')

    main(start_urls_list, max_pages_to_crawl_per_source, concurrent_workers)
