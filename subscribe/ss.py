import requests
from urllib.parse import urlparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading

# 请求头 (Request Headers)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 配置参数 (Configuration Parameters)
TIMEOUT = 30         # 单次请求超时时间（秒）
OUTPUT_FILE = 'data/ss.txt' # 输出文件路径

# 确定并发线程数
cpu_cores = os.cpu_count()
if cpu_cores is None:
    MAX_WORKERS = 16
else:
    MAX_WORKERS = min(32, cpu_cores + 4)

def is_valid_url(url):
    """验证URL格式是否合法"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def get_url_list(source_url):
    """从单个源URL获取URL列表"""
    print(f"正在从源获取URL列表: {source_url}")
    try:
        response = requests.get(source_url, headers=headers, timeout=60)
        response.raise_for_status()
        raw_urls = response.text.splitlines()
        valid_urls = [url.strip() for url in raw_urls if is_valid_url(url.strip())]
        print(f"从 {source_url} 获取到 {len(valid_urls)} 个有效URL")
        return valid_urls
    except Exception as e:
        print(f"获取URL列表失败 ({source_url}): {e}")
        return []

def process_url(url):
    """
    处理单个URL，获取内容。
    成功则返回解码后的内容，失败则返回None。
    """
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        
        text_content = resp.text
        if len(text_content.strip()) < 10 or "DOMAIN" in text_content or "port" in text_content or "proxies" in text_content:
            return None
        
        try:
            decoded_content = base64.b64decode(text_content).decode('utf-8')
            return decoded_content
        except base64.binascii.Error:
            return None
        except UnicodeDecodeError:
            return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None

# 主程序
source_urls = [
    'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/xujw3.txt',
    'https://github.com/mermeroo/V2RAY-CLASH-BASE64-Subscription.Links/raw/refs/heads/main/SUB%20LINKS',
    # 可添加更多源URL
]

print(f"开始处理URL。单个URL超时: {TIMEOUT}秒, 最大并发线程数: {MAX_WORKERS}")

# 获取所有有效URL
all_valid_urls = []
for source_url in source_urls:
    valid_urls_from_source = get_url_list(source_url)
    all_valid_urls.extend(valid_urls_from_source)

if not all_valid_urls:
    print("没有获取到任何有效URL，程序退出。")
    exit()

print(f"总共获取到 {len(all_valid_urls)} 个有效URL，准备处理...")

# 确保输出目录存在
output_dir = os.path.dirname(OUTPUT_FILE)
if output_dir:
    os.makedirs(output_dir, exist_ok=True)

# 用于记录唯一节点的集合和锁
unique_nodes = set()
lock = threading.Lock()

# 处理URL并保存唯一内容
success_count = 0
processed_count = 0

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_file:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in all_valid_urls}
        total_tasks = len(future_to_url)
        print(f"已提交 {total_tasks} 个任务到线程池进行处理。")

        for i, future in enumerate(as_completed(future_to_url)):
            url_processed = future_to_url[future]
            processed_count += 1
            
            try:
                content = future.result()
                if content:
                    lines = content.splitlines()
                    for line in lines:
                        line = line.strip()
                        if line:  # 跳过空行
                            with lock:
                                if line not in unique_nodes:
                                    unique_nodes.add(line)
                                    out_file.write(line + '\n')
                                    success_count += 1
            except Exception as exc:
                print(f"URL {url_processed} 在执行期间产生错误: {exc}")
            
            if processed_count % 10 == 0 or processed_count == total_tasks:
                print(f"[进度] 已处理 {processed_count}/{total_tasks} 个 | 唯一节点数 {success_count}")

# 最终报告
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"尝试处理URL总数：{len(all_valid_urls)}")
print(f"实际完成处理数：{processed_count}")
print(f"成功写入的唯一节点数：{success_count}")
if processed_count > 0:
    print(f"有效内容率（基于完成任务）：{success_count/processed_count:.1%}")
else:
    print("没有处理任何URL。")
print(f"结果文件已保存至：{OUTPUT_FILE}")
