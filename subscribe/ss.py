import requests
from urllib.parse import urlparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading
import re # 新增导入
import json # 新增导入

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
        # 过滤掉明显无效或非节点内容
        if len(text_content.strip()) < 10 or "DOMAIN" in text_content or "port" in text_content or "proxies" in text_content:
            return None
        
        try:
            # 尝试Base64解码
            decoded_content = base64.b64decode(text_content).decode('utf-8')
            return decoded_content
        except base64.binascii.Error: # Base64解码错误
            # 如果解码失败，可能是纯文本节点列表，直接返回原始文本
            # 但要确保它不是我们之前过滤掉的那些短内容或关键词内容
            if len(text_content.strip()) >= 10 and not ("DOMAIN" in text_content or "port" in text_content or "proxies" in text_content):
                 return text_content # 返回原始文本
            return None
        except UnicodeDecodeError: # 解码后的文本非UTF-8
            return None
    except requests.exceptions.Timeout:
        # print(f"URL {url} 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        # print(f"URL {url} 请求失败: {e}")
        return None
    except Exception:
        # print(f"URL {url} 处理时发生未知错误: {e}")
        return None

def get_node_key(node_line):
    """
    为代理节点字符串生成一个唯一的键，用于去重。
    键的组成部分: (协议, 标识符, 小写的服务器主机名, 端口)
    如果解析失败，则返回原始 node_line 作为后备。
    """
    node_line = node_line.strip()
    original_node_for_fallback = node_line # 用于解析失败时的后备

    try:
        if '://' not in node_line:
            return original_node_for_fallback # 没有协议分隔符，无法解析

        protocol_part, rest = node_line.split('://', 1)
        protocol = protocol_part.lower()

        # 首先移除 #fragment (节点名称/备注)
        if '#' in rest:
            rest_no_fragment, _ = rest.split('#', 1)
        else:
            rest_no_fragment = rest
        
        if protocol == 'vmess':
            try:
                encoded_json = rest_no_fragment
                # 如果需要，填充base64字符串
                missing_padding = len(encoded_json) % 4
                if missing_padding:
                    encoded_json += '=' * (4 - missing_padding)
                
                decoded_json_str = base64.b64decode(encoded_json).decode('utf-8')
                config = json.loads(decoded_json_str)
                
                uuid = config.get('id')
                server_address = str(config.get('add', '')).lower().rstrip('.')
                port = str(config.get('port', ''))

                if uuid and server_address and port:
                    return ('vmess', uuid, server_address, port)
            except Exception: # 捕获JSON, Base64或其他错误
                pass # 失败则继续，使用默认键

        elif protocol in ['ss', 'vless', 'hysteria2']:
            # 类URI结构: 认证信息@主机信息?查询参数
            if '@' not in rest_no_fragment:
                 return original_node_for_fallback # 缺少关键的 '@' 分隔符

            auth_part, host_spec_part = rest_no_fragment.split('@', 1)

            # 忽略查询参数部分 (如 ?sni=...)
            if '?' in host_spec_part:
                host_and_port_part, _ = host_spec_part.split('?', 1)
            else:
                host_and_port_part = host_spec_part
            
            server_host = ""
            server_port = ""

            # 从后向前查找冒号以分离主机和端口 (处理IPv6地址)
            last_colon_idx = host_and_port_part.rfind(':')
            if last_colon_idx != -1:
                potential_host = host_and_port_part[:last_colon_idx]
                potential_port = host_and_port_part[last_colon_idx+1:]
                if potential_port.isdigit(): # 确保冒号后面是数字端口
                    server_port = potential_port
                    server_host = potential_host
                    # 处理带方括号的IPv6地址
                    if server_host.startswith('[') and server_host.endswith(']'):
                        server_host = server_host[1:-1]
                    server_host = server_host.lower().rstrip('.') # 小写并移除末尾的点
                else: #最后的冒号不是端口分隔符 (例如，IPv6地址本身可能包含冒号但没有端口)
                    server_host = host_and_port_part.lower().rstrip('.')
            else: # 没有冒号，假定整个部分是主机，端口缺失
                server_host = host_and_port_part.lower().rstrip('.')

            if not server_host or not server_port: # 缺少主机或端口，无法构成有效键
                return original_node_for_fallback

            identifier = auth_part # 对于ss是base64串; 对于vless/hysteria2是UUID/认证串
            if identifier: # 确保标识符存在
                return (protocol, identifier, server_host, server_port)
        
    except ValueError: # 主要捕获 split 操作的错误
        pass 
    except Exception: # 捕获解析过程中的任何其他意外错误
        pass 

    # 如果以上所有解析尝试都失败，返回原始节点字符串
    return original_node_for_fallback


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
if output_dir and not os.path.exists(output_dir): # 只有在目录非空且不存在时创建
    os.makedirs(output_dir, exist_ok=True)

# 用于记录唯一键的集合和锁
unique_keys = set() # 从 unique_nodes 改为 unique_keys
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
                            key = get_node_key(line) # 为节点行生成唯一的键
                            with lock:
                                if key not in unique_keys: # 检查键是否已存在
                                    unique_keys.add(key)   # 将键添加到集合中
                                    out_file.write(line + '\n') # 写入原始的节点行
                                    success_count += 1
            except Exception as exc:
                print(f"URL {url_processed} 在执行期间产生错误: {exc}")
            
            # 每处理10个或处理完所有任务时打印进度
            if processed_count % 10 == 0 or processed_count == total_tasks:
                print(f"[进度] 已处理 {processed_count}/{total_tasks} 个 | 唯一节点数 {success_count}")

# 最终报告
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"尝试处理URL总数：{len(all_valid_urls)}")
print(f"实际完成处理数：{processed_count}")
print(f"成功写入的唯一节点数：{success_count}")
if processed_count > 0:
    # 避免除以零错误
    valid_content_rate = (success_count / processed_count * 100) if processed_count > 0 else 0
    print(f"有效内容率（基于完成任务）：{valid_content_rate:.1f}%")
else:
    print("没有处理任何URL。")
print(f"结果文件已保存至：{OUTPUT_FILE}")
