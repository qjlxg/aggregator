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

# 加载环境变量
load_dotenv()

# 从环境变量中读取私有仓库 API 基本地址和 PAT
# 例如 ALL_CLASH_BASE_URL=https://api.github.com/repos/qjlxg/362/contents/ss-url
ALL_CLASH_BASE_URL = os.environ.get("ALL_CLASH_BASE_URL")
GIST_PAT = os.environ.get("GIST_PAT")

# 拼接 API URL（使用 main 分支，如有需要请修改 ref 参数）
PRIVATE_API_URL = f"{ALL_CLASH_BASE_URL}?ref=main"

# 配置日志
logging.basicConfig(filename='error.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# 请求头中加入 Authorization 以访问私有仓库
headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/91.0.4472.124 Safari/537.36'
    ),
    'Accept-Encoding': 'gzip, deflate',
    'Authorization': f"token {GIST_PAT}"
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
    """
    通过GitHub API获取私有仓库中存放URL列表的文件内容，
    并返回拆分后的列表。文件内容由 API 返回的JSON中的 content 字段取得，
    该字段为base64编码的内容。
    """
    try:
        response = requests.get(url_source, headers=headers, timeout=10)
        response.raise_for_status()
        # API返回的是JSON数据
        data = response.json()
        if 'content' not in data:
            print("未在返回数据中找到内容字段。")
            return []
        # GitHub API返回的content字段中可能包含换行符，先去除换行再base64解码
        encoded_content = data['content'].replace("\n", "")
        decoded_bytes = base64.b64decode(encoded_content)
        text_content = decoded_bytes.decode('utf-8').strip()
        # 将内容按行拆分，并过滤空行
        raw_urls = [line.strip() for line in text_content.splitlines() if line.strip()]
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

# URL 来源列表，使用从私有仓库中获取URL列表的文件的API URL
url_sources = [
    PRIVATE_API_URL,
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
