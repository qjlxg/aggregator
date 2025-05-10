import requests
from urllib.parse import urlparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import yaml # Added for YAML processing

# 请求头 (Request Headers)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 配置参数 (Configuration Parameters)
TIMEOUT = 30         # 单次请求超时时间（秒）- Greatly reduced for faster failing on unresponsive URLs
OUTPUT_FILE = 'data/ss.txt' # Make sure 'data' directory can be created or exists

# Determine a reasonable number of worker threads for concurrency
cpu_cores = os.cpu_count()
if cpu_cores is None:
    MAX_WORKERS = 16 # Default if cpu_count is not available
else:
    MAX_WORKERS = min(32, cpu_cores + 4) # Cap at 32, or slightly more than CPU cores

# URLs to exclude from the YAML source
YAML_EXCLUDED_PREFIXES = [
    "https://raw.githubusercontent.com",
    "https://t.me",
    "https://github.com" # Covers both instances in the request
]

def is_valid_url(url):
    """验证URL格式是否合法 (Validate if URL format is legal)"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def get_url_list_from_txt(source_url):
    """从单个文本源URL获取URL列表 (Get URL list from a single text source URL)"""
    print(f"正在从文本源获取URL列表: {source_url}")
    try:
        response = requests.get(source_url, headers=headers, timeout=60)
        response.raise_for_status() # Raise an exception for HTTP errors
        raw_urls = response.text.splitlines()
        valid_urls = [url.strip() for url in raw_urls if is_valid_url(url.strip())]
        print(f"从 {source_url} 获取到 {len(valid_urls)} 个有效URL")
        return valid_urls
    except Exception as e:
        print(f"获取文本URL列表失败 ({source_url}): {e}")
        return []

def get_urls_from_yaml_source(yaml_url, excluded_prefixes):
    """
    从单个YAML源URL获取并过滤URL列表。
    (Get and filter URL list from a single YAML source URL)
    """
    print(f"正在从YAML源获取URL列表: {yaml_url}")
    filtered_urls = []
    try:
        response = requests.get(yaml_url, headers=headers, timeout=60)
        response.raise_for_status()
        content = response.text
        
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            print(f"解析YAML失败 ({yaml_url}): {e}")
            return []

        if not isinstance(data, list):
            print(f"YAML内容格式非预期 (不是列表): {yaml_url}")
            return []
            
        extracted_count = 0
        # Iterate through the YAML data to find URLs
        # Assuming the YAML structure is a list of dictionaries,
        # and each dictionary might contain a 'url' key with a string value.
        # This part might need adjustment based on the exact YAML structure.
        for item in data:
            if isinstance(item, dict):
                url_value = item.get('url') # Common key for URLs in such configs
                if isinstance(url_value, str):
                    extracted_count +=1
                    url_candidate = url_value.strip()
                    if is_valid_url(url_candidate):
                        is_excluded = False
                        for prefix in excluded_prefixes:
                            if url_candidate.startswith(prefix):
                                is_excluded = True
                                break
                        if not is_excluded:
                            filtered_urls.append(url_candidate)
                    # else: # Optional: log invalid URL format from YAML
                        # print(f"从YAML中提取的无效URL格式: {url_candidate}") 
                # Add more checks here if URLs are nested deeper or have different keys
            # If URLs are just strings in a list directly:
            # elif isinstance(item, str):
            #     url_candidate = item.strip()
            #     if is_valid_url(url_candidate):
            #         is_excluded = False
            #         for prefix in excluded_prefixes:
            #             if url_candidate.startswith(prefix):
            #                 is_excluded = True
            #                 break
            #         if not is_excluded:
            #             filtered_urls.append(url_candidate)


        print(f"从 {yaml_url} 提取到 {extracted_count} 个URL，过滤后剩余 {len(filtered_urls)} 个有效URL")
        return filtered_urls
        
    except requests.exceptions.RequestException as e:
        print(f"获取YAML内容失败 ({yaml_url}): {e}")
        return []
    except Exception as e:
        print(f"处理YAML源时发生未知错误 ({yaml_url}): {e}")
        return []


def process_url(url):
    """
    处理单个URL，获取内容。 (Process a single URL, get content)
    成功则返回解码后的内容，失败则返回None。 (Return decoded content on success, None on failure)
    """
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
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
text_source_urls = [
    'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/subscribes.txt',
    # 你可以在这里添加更多的文本源URL (You can add more text source URLs here)
]

yaml_source_urls = [
    'https://github.com/qjlxg/collectSub/raw/refs/heads/main/config.yaml',
    # 你可以在这里添加更多的YAML源URL (You can add more YAML source URLs here)
]

print(f"开始处理URL。单个URL超时: {TIMEOUT}秒, 最大并发线程数: {MAX_WORKERS}")

# 获取所有有效的URL (Get all valid URLs)
all_valid_urls = []

# Process text-based URL sources
for source_url in text_source_urls:
    valid_urls_from_source = get_url_list_from_txt(source_url)
    all_valid_urls.extend(valid_urls_from_source)

# Process YAML-based URL sources
for yaml_s_url in yaml_source_urls:
    valid_urls_from_yaml = get_urls_from_yaml_source(yaml_s_url, YAML_EXCLUDED_PREFIXES)
    all_valid_urls.extend(valid_urls_from_yaml)


if not all_valid_urls:
    print("没有获取到任何有效URL，程序退出。(No valid URLs obtained, program will exit.)")
    exit()

# Remove duplicates that might have come from different sources
all_valid_urls = sorted(list(set(all_valid_urls)))
print(f"去除重复后，总共获取到 {len(all_valid_urls)} 个有效URL，准备处理...")


# 处理URL并保存内容 (Process URLs and save content)
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

# 最终报告 (Final Report)
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"尝试处理URL总数 (Total unique URLs submitted for processing)：{len(all_valid_urls)}")
print(f"实际完成处理数 (Actually completed processing)：{processed_count}")
print(f"成功获取内容数 (Successfully fetched content)：{success_count}")
if processed_count > 0:
    print(f"有效内容率 (Success rate based on completed tasks)：{success_count/processed_count:.1%}")
else:
    print("没有处理任何URL (No URLs were processed).")
print(f"结果文件已保存至 (Results saved to)：{OUTPUT_FILE}")
