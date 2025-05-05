# -*- coding: utf-8 -*-
import os
import requests
from urllib.parse import urlparse
import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import argparse
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()


ALL_CLASH_BASE_URL = os.environ.get("ALL_CLASH_BASE_URL")
GIST_PAT = os.environ.get("GIST_PAT")


PRIVATE_URL = f"{ALL_CLASH_BASE_URL}?token={GIST_PAT}"

# 配置日志
logging.basicConfig(filename='error.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/91.0.4472.124 Safari/537.36'
    ),
    'Accept-Encoding': 'gzip, deflate'
}

# 命令行参数
parser = argparse.ArgumentParser(description="URL内容获取脚本，支持多个URL来源")
parser.add_argument('--max_success', type=int, default=99999, help="目标成功数量")
parser.add_argument('--timeout', type=int, default=60, help="请求超时时间（秒）")
parser.add_argument('--output', type=str, default='data/all_clash.txt', help="输出文件路径")
args = parser.parse_args()

MAX_SUCCESS = args.max_success
TIMEOUT = args.timeout
OUTPUT_FILE = args.output

def is_valid_url(url):
    """验证URL格式是否合法"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False

def get_url_list(url_source):
    """从单个URL来源获取URL列表"""
    try:
        response = requests.get(url_source, headers=headers, timeout=10)
        response.raise_for_status()
        raw_urls = [line.strip() for line in response.text.splitlines() if line.strip()]
        print(f"从 {url_source} 获取到 {len(raw_urls)} 个URL")
        return raw_urls
    except Exception as e:
        logging.error(f"获取URL列表失败: {url_source} - {e}")
        return []

def fetch_url(url):
    """获取并处理单个URL的内容"""
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        content = resp.text.strip()
        # 过滤明显无效内容
        if len(content) < 10 or any(x in content for x in ["DOMAIN", "port", "proxies", "[]", "{}"]):
            return None
        # 尝试base64解码
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            return decoded_content
        except Exception:
            # 如果不是base64编码，则直接返回原内容
            return content if len(content) > 10 else None
    except Exception as e:
        logging.error(f"处理失败: {url} - {e}")
        return None

# URL 来源列表，这里使用通过环境变量隐藏后的私有仓库文件 URL
url_sources = [
    PRIVATE_URL,
]

# 获取所有URL来源的URL列表
all_raw_urls = []
for source in url_sources:
    raw_urls = get_url_list(source)
    all_raw_urls.extend(raw_urls)

# 去重并验证URL格式
unique_urls = list({url.strip() for url in all_raw_urls if url.strip()})
valid_urls = [url for url in unique_urls if is_valid_url(url)]
print(f"合并后唯一URL数量：{len(unique_urls)}")
print(f"经过格式验证的有效URL数量：{len(valid_urls)}")

# 确保输出目录存在
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# 处理URL内容
success_count = 0
with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_file:
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in valid_urls}
        for future in tqdm(as_completed(future_to_url), total=len(valid_urls), desc="处理URL"):
            result = future.result()
            if result and success_count < MAX_SUCCESS:
                out_file.write(result.strip() + '\n')
                success_count += 1

# 最终结果报告
print("\n" + "=" * 50)
print("最终结果：")
print(f"处理URL总数：{len(valid_urls)}")
print(f"成功获取内容数：{success_count}")
if len(valid_urls) > 0:
    print(f"有效内容率：{success_count/len(valid_urls):.1%}")
if success_count < MAX_SUCCESS:
    print("警告：未能达到目标数量，原始列表可能有效URL不足")
print(f"结果文件已保存至：{OUTPUT_FILE}")
