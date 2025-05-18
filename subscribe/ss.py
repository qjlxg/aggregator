import requests
from urllib.parse import urlparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading
import re
import json

# 请求头 (Request Headers)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 配置参数 (Configuration Parameters)
TIMEOUT = 30         # 单次请求超时时间（秒）
FINAL_OUTPUT_FILE = 'data/ss.txt' # 最终输出文件路径
TEMP_OUTPUT_FILE = 'data/ss_temp_all_nodes.txt' # 临时存储所有节点的路径

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
    成功则返回解码后的内容(字符串形式，可能包含多行)，失败则返回None。
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
            if len(text_content.strip()) >= 10 and not ("DOMAIN" in text_content or "port" in text_content or "proxies" in text_content):
                 return text_content
            return None
        except UnicodeDecodeError:
            return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None

def get_node_key(node_line):
    """
    为代理节点字符串生成一个唯一的键，用于去重。
    键的组成部分: (协议, 标识符, 小写的服务器主机名, 端口)
    如果解析失败，则返回原始 node_line 作为后备。
    """
    node_line = node_line.strip()
    original_node_for_fallback = node_line

    try:
        if '://' not in node_line:
            return original_node_for_fallback

        protocol_part, rest = node_line.split('://', 1)
        protocol = protocol_part.lower()

        if '#' in rest:
            rest_no_fragment, _ = rest.split('#', 1)
        else:
            rest_no_fragment = rest
        
        if protocol == 'vmess':
            try:
                encoded_json = rest_no_fragment
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
            except Exception:
                pass

        elif protocol in ['ss', 'vless', 'hysteria2']:
            if '@' not in rest_no_fragment:
                 return original_node_for_fallback

            auth_part, host_spec_part = rest_no_fragment.split('@', 1)

            if '?' in host_spec_part:
                host_and_port_part, _ = host_spec_part.split('?', 1)
            else:
                host_and_port_part = host_spec_part
            
            server_host = ""
            server_port = ""

            last_colon_idx = host_and_port_part.rfind(':')
            if last_colon_idx != -1:
                potential_host = host_and_port_part[:last_colon_idx]
                potential_port = host_and_port_part[last_colon_idx+1:]
                if potential_port.isdigit():
                    server_port = potential_port
                    server_host = potential_host
                    if server_host.startswith('[') and server_host.endswith(']'):
                        server_host = server_host[1:-1]
                    server_host = server_host.lower().rstrip('.')
                else:
                    server_host = host_and_port_part.lower().rstrip('.')
            else:
                server_host = host_and_port_part.lower().rstrip('.')

            if not server_host or not server_port:
                return original_node_for_fallback

            identifier = auth_part
            if identifier:
                return (protocol, identifier, server_host, server_port)
        
    except ValueError:
        pass 
    except Exception:
        pass 

    return original_node_for_fallback

# --- 主程序 ---
source_urls = [
    'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/xujw3.txt',
    'https://github.com/mermeroo/V2RAY-CLASH-BASE64-Subscription.Links/raw/refs/heads/main/SUB%20LINKS',
    # 可添加更多源URL
]

print(f"开始处理URL。单个URL超时: {TIMEOUT}秒, 最大并发线程数: {MAX_WORKERS}")

# 获取所有有效订阅链接URL
all_subscription_urls = []
for source_url in source_urls:
    subscription_urls_from_source = get_url_list(source_url)
    all_subscription_urls.extend(subscription_urls_from_source)

if not all_subscription_urls:
    print("没有获取到任何有效订阅链接URL，程序退出。")
    exit()

print(f"总共获取到 {len(all_subscription_urls)} 个有效订阅链接URL，准备处理...")

# 确保输出目录存在
output_dir = os.path.dirname(FINAL_OUTPUT_FILE)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)

temp_output_dir = os.path.dirname(TEMP_OUTPUT_FILE)
if temp_output_dir and not os.path.exists(temp_output_dir):
    os.makedirs(temp_output_dir, exist_ok=True)


# --- 阶段 1: 从URL收集所有节点到临时文件 ---
print("\n--- 阶段 1: 开始收集所有节点 ---")
all_raw_lines_collected = []
processed_url_count = 0
urls_yielded_content = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    future_to_url = {executor.submit(process_url, url): url for url in all_subscription_urls}
    total_tasks = len(future_to_url)
    print(f"已提交 {total_tasks} 个订阅链接到线程池进行处理。")

    for i, future in enumerate(as_completed(future_to_url)):
        url_processed = future_to_url[future]
        processed_url_count += 1
        
        try:
            content = future.result()
            if content:
                urls_yielded_content += 1
                lines = content.splitlines()
                for line in lines:
                    stripped_line = line.strip()
                    if stripped_line: # 跳过空行
                        all_raw_lines_collected.append(stripped_line)
        except Exception as exc:
            print(f"订阅链接 {url_processed} 在执行期间产生错误: {exc}")
        
        if processed_url_count % 10 == 0 or processed_url_count == total_tasks:
            print(f"[阶段1 进度] 已处理 {processed_url_count}/{total_tasks} 个订阅链接 | 已收集 {len(all_raw_lines_collected)} 条原始节点")

# 将所有收集到的原始节点写入临时文件
with open(TEMP_OUTPUT_FILE, 'w', encoding='utf-8') as temp_file:
    for line in all_raw_lines_collected:
        temp_file.write(line + '\n')

print(f"--- 阶段 1 完成 ---")
print(f"总共处理了 {processed_url_count} 个订阅链接。")
print(f"{urls_yielded_content} 个订阅链接成功返回了内容。")
print(f"总共收集到 {len(all_raw_lines_collected)} 条原始节点数据，已保存到临时文件: {TEMP_OUTPUT_FILE}")


# --- 阶段 2: 从临时文件读取，去重并保存到最终文件 ---
print("\n--- 阶段 2: 开始去重并生成最终输出 ---")
unique_keys = set()
final_unique_nodes_written = 0

if not os.path.exists(TEMP_OUTPUT_FILE):
    print(f"错误：临时文件 {TEMP_OUTPUT_FILE} 未找到。无法进行去重。")
    exit()

try:
    with open(TEMP_OUTPUT_FILE, 'r', encoding='utf-8') as temp_file, \
         open(FINAL_OUTPUT_FILE, 'w', encoding='utf-8') as out_file:
        
        line_num = 0
        for line_content in temp_file:
            line_num +=1
            node_line = line_content.strip()
            if node_line:
                key = get_node_key(node_line)
                if key not in unique_keys:
                    unique_keys.add(key)
                    out_file.write(node_line + '\n')
                    final_unique_nodes_written += 1
            
            if line_num % 500 == 0 : # 每处理500行临时文件内容打印一次进度
                print(f"[阶段2 进度] 已处理临时文件 {line_num} 行 | 当前唯一节点数 {final_unique_nodes_written}")


    print(f"--- 阶段 2 完成 ---")
    print(f"成功从 {len(all_raw_lines_collected)} 条原始节点中提取并写入 {final_unique_nodes_written} 条唯一节点。")

finally:
    # 清理临时文件
    if os.path.exists(TEMP_OUTPUT_FILE):
        try:
            os.remove(TEMP_OUTPUT_FILE)
            print(f"临时文件 {TEMP_OUTPUT_FILE} 已成功删除。")
        except OSError as e:
            print(f"删除临时文件 {TEMP_OUTPUT_FILE} 失败: {e}")


# --- 最终报告 ---
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"尝试处理订阅链接总数：{len(all_subscription_urls)}")
print(f"实际完成处理的订阅链接数：{processed_url_count}")
print(f"返回内容的订阅链接数：{urls_yielded_content}")
print(f"收集到的原始节点总数（去重前）：{len(all_raw_lines_collected)}")
print(f"成功写入的唯一节点数（去重后）：{final_unique_nodes_written}")

if len(all_raw_lines_collected) > 0:
    deduplication_rate = (1 - (final_unique_nodes_written / len(all_raw_lines_collected))) * 100 if len(all_raw_lines_collected) > 0 else 0
    print(f"节点去重率：{deduplication_rate:.1f}%")
else:
    print("没有收集到任何原始节点数据。")

if processed_url_count > 0 and urls_yielded_content > 0 : # 避免除以零
    unique_node_yield_rate = (final_unique_nodes_written / urls_yielded_content) if urls_yielded_content > 0 else 0 # 平均每个有效源产出多少唯一节点
    # print(f"平均每个有效源产出唯一节点数: {unique_node_yield_rate:.1f}") # 这项指标意义可能不大
    pass

print(f"最终结果文件已保存至：{FINAL_OUTPUT_FILE}")
