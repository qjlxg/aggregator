import requests
from urllib.parse import urlparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# --- 新增：从环境变量或安全配置中获取 GITHUB PAT ---
# 强烈建议不要直接将 PAT 硬编码到脚本中，尤其是当脚本会被共享或提交到版本控制时。
# 最好将其存储在环境变量中。
GITHUB_TOKEN = os.getenv('OKEN') # 例如，你可以在运行脚本前设置环境变量 MY_GITHUB_PAT

# 如果没有设置环境变量，你可以在这里临时硬编码（仅供测试，不推荐用于生产）
# if not GITHUB_TOKEN:
#     GITHUB_TOKEN = "ghp_YOUR_PERSONAL_ACCESS_TOKEN_HERE" # <--- 用你的真实 PAT 替换

# 请求头 (Request Headers)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 如果 GITHUB_TOKEN 存在，则添加到请求头中用于授权
if GITHUB_TOKEN:
    headers['Authorization'] = f'token {GITHUB_TOKEN}'
else:
    print("警告：未配置GITHUB_TOKEN。如果访问私有仓库，请求将会失败。")
    # 你可以选择在这里退出脚本，或者让它继续尝试（但可能会失败）
    # exit("错误：GITHUB_TOKEN 未设置，无法访问私有仓库。")


# 配置参数 (Configuration Parameters)
TIMEOUT = 30
OUTPUT_FILE = 'data/ss.txt'
cpu_cores = os.cpu_count()
if cpu_cores is None:
    MAX_WORKERS = 16
else:
    MAX_WORKERS = min(32, cpu_cores + 4)

def is_valid_url(url):
    """验证URL格式是否合法 (Validate if URL format is legal)"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def get_url_list(source_url):
    """从单个源URL获取URL列表 (Get URL list from a single source URL)"""
    print(f"正在从源获取URL列表: {source_url}")
    try:
        # 注意这里的 headers 已经包含了 Authorization (如果 GITHUB_TOKEN 被设置了)
        response = requests.get(source_url, headers=headers, timeout=60)
        response.raise_for_status() # Raise an exception for HTTP errors
        raw_urls = response.text.splitlines()
        valid_urls = [url.strip() for url in raw_urls if is_valid_url(url.strip())]
        print(f"从 {source_url} 获取到 {len(valid_urls)} 个有效URL")
        return valid_urls
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"获取URL列表失败 ({source_url}): 404 Not Found。请检查URL是否正确，以及对于私有仓库是否提供了有效的 GitHub Token。")
        elif e.response.status_code == 401:
            print(f"获取URL列表失败 ({source_url}): 401 Unauthorized。提供的 GitHub Token 可能无效或权限不足。")
        else:
            print(f"获取URL列表时发生HTTP错误 ({source_url}): {e}")
        return []
    except Exception as e:
        print(f"获取URL列表失败 ({source_url}): {e}")
        return []

def process_url(url):
    """
    处理单个URL，获取内容。 (Process a single URL, get content)
    成功则返回解码后的内容，失败则返回None。 (Return decoded content on success, None on failure)
    """
    try:
        # 注意这里的 headers 已经包含了 Authorization (如果 GITHUB_TOKEN 被设置了)
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

# 主程序 (Main Program)
source_urls = [
    # 确保这个URL是正确的，并且如果它是私有的，你已经正确设置了 GITHUB_TOKEN
    'https://github.com/qjlxg/362/raw/refs/heads/main/data/subscribes.txt',
]

print(f"开始处理URL。单个URL超时: {TIMEOUT}秒, 最大并发线程数: {MAX_WORKERS}")
if GITHUB_TOKEN:
    print("已配置 GitHub Token 进行授权访问。")

all_valid_urls = []
for source_url in source_urls:
    valid_urls_from_source = get_url_list(source_url)
    all_valid_urls.extend(valid_urls_from_source)

if not all_valid_urls:
    print("没有获取到任何有效URL，程序退出。(No valid URLs obtained, program will exit.)")
    exit()

print(f"总共获取到 {len(all_valid_urls)} 个有效URL，准备处理...")

success_count = 0
processed_count = 0

output_dir = os.path.dirname(OUTPUT_FILE)
if output_dir:
    os.makedirs(output_dir, exist_ok=True)

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
                    out_file.write(content)
                    if not content.endswith('\n'):
                        out_file.write('\n')
                    success_count += 1
            except Exception as exc:
                print(f"URL {url_processed} 在执行期间产生错误: {exc}")
            
            if processed_count % 10 == 0 or processed_count == total_tasks:
                print(f"[进度] 已处理 {processed_count}/{total_tasks} 个 | 成功 {success_count} 个")

print("\n" + "=" * 50)
print(f"最终结果：")
print(f"尝试处理URL总数 (Total URLs submitted for processing)：{len(all_valid_urls)}")
print(f"实际完成处理数 (Actually completed processing)：{processed_count}")
print(f"成功获取内容数 (Successfully fetched content)：{success_count}")
if processed_count > 0:
    print(f"有效内容率 (Success rate based on completed tasks)：{success_count/processed_count:.1%}")
else:
    print("没有处理任何URL (No URLs were processed).")
print(f"结果文件已保存至 (Results saved to)：{OUTPUT_FILE}")
