import os
import re
import subprocess
import socket
import time
from datetime import datetime
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义聚合URLs的来源
AGGREGATOR_URLS = [
    "https://raw.githubusercontent.com/iptv-org/iptv/master/README.md",
]

# 用于匹配包含 m3u/m3u8/txt 扩展名的URL
URL_PATTERN = re.compile(r'https?://[^\s"<>()]*?\.(m3u|m3u8|txt)(?:\?.*?)?(?:#[^\s"<>]*?)?')

# --- 辅助函数 ---

def read_txt_to_array(file_name):
    """从TXT文件中读取内容，每行一个元素"""
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            lines = [line.strip() for line in lines if line.strip()]
            return lines
    except FileNotFoundError:
        logging.error(f"文件 '{file_name}' 未找到。")
        return []
    except Exception as e:
        logging.error(f"读取文件 '{file_name}' 时发生错误: {e}")
        return []

def get_url_file_extension(url):
    """获取URL中的文件扩展名"""
    parsed_url = urlparse(url)
    extension = os.path.splitext(parsed_url.path)[1].lower() # 转换为小写
    return extension

def convert_m3u_to_txt(m3u_content):
    """将m3u/m3u8内容转换为频道名称和地址的txt格式"""
    lines = m3u_content.split('\n')
    txt_lines = []
    channel_name = ""
    for line in lines:
        line = line.strip() # 清理空白符
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            # 提取频道名称，通常在逗号后面
            match = re.search(r'#EXTINF:.*?\,(.*)', line)
            if match:
                channel_name = match.group(1).strip()
            else:
                channel_name = "未知频道" # 默认名称
        elif line and not line.startswith('#'): # 确保是URL行且不是注释行
            # 允许 http, rtmp, p3p 等协议
            if channel_name: # 确保有频道名称
                txt_lines.append(f"{channel_name},{line}")
            channel_name = "" # 重置名称，等待下一个 #EXTINF
    return '\n'.join(txt_lines)

def clean_url_params(url):
    """清理URL中的查询参数和片段标识符，只保留基础URL"""
    parsed_url = urlparse(url)
    # 移除查询参数和片段
    return parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True, retry=retry_if_exception_type(requests.exceptions.RequestException))
def fetch_url_content_with_retry(url, timeout=15):
    """使用 requests 库获取URL内容，并进行重试"""
    logging.info(f"尝试获取 URL: {url} (超时: {timeout}s)")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()  # 如果状态码不是 2xx，则抛出 HTTPError
    return response.text

def process_url(url):
    """处理单个URL，获取频道名称和地址"""
    try:
        text = fetch_url_content_with_retry(url)

        # 如果是m3u/m3u8文件，先转换为txt格式
        if get_url_file_extension(url) in [".m3u", ".m3u8"]:
            text = convert_m3u_to_txt(text)

        lines = text.split('\n')
        channel_count = 0
        for line in lines:
            line = line.strip()
            # 过滤包含 "#genre#" 的行，并确保行中包含逗号和协议
            if "#genre#" not in line and "," in line and "://" in line:
                parts = line.split(',', 1) # 只按第一个逗号分割
                channel_name = parts[0].strip()
                channel_address_raw = parts[1].strip()

                # 处理一行中可能包含多个URL的情况，以 '#' 分隔
                if '#' in channel_address_raw:
                    url_list = channel_address_raw.split('#')
                    for channel_url in url_list:
                        channel_url = clean_url_params(channel_url.strip())
                        if channel_url: # 确保URL不为空
                            yield channel_name, channel_url
                            channel_count += 1
                else:
                    channel_url = clean_url_params(channel_address_raw)
                    if channel_url: # 确保URL不为空
                        yield channel_name, channel_url
                        channel_count += 1
        logging.info(f"成功读取 URL: {url}，获取到频道列表: {channel_count} 条")
    except requests.exceptions.RequestException as e:
        logging.error(f"处理 URL 时发生请求错误 (重试后失败)：{url} - {e}")
    except Exception as e:
        logging.error(f"处理 URL 时发生未知错误：{url} - {e}")

def filter_and_modify_sources(corrections):
    """过滤和修改频道名称和URL"""
    filtered_corrections = []
    # 您的过滤词列表，我保持不变
    name_dict = ['购物', '理财', '导视', '指南', '测试', '芒果', 'CGTN','(480p)','(360p)','(240p)','(406p)',' (540p)','(600p)','(576p)','[Not 24/7]','DJ','音乐','演唱会','舞曲','春晚','格斗','粤','祝','体育','广播','博斯','神话']
    url_dict = [] # 您的 URL 过滤列表，原脚本是空的，这里也保持空

    for name, url in corrections:
        # 检查名称或URL是否包含过滤词
        if any(word.lower() in name.lower() for word in name_dict) or \
           any(word in url for word in url_dict):
            logging.info(f"过滤频道: {name},{url}")
        else:
            # 清理频道名称中的特定字符串
            name = name.replace("FHD", "").replace("HD", "").replace("hd", "").replace("频道", "").replace("高清", "") \
                .replace("超清", "").replace("20M", "").replace("-", "").replace("4k", "").replace("4K", "") \
                .replace("4kR", "")
            filtered_corrections.append((name, url))
    return filtered_corrections

def clear_txt_files(directory):
    """删除指定目录下所有TXT文件"""
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
                logging.info(f"已删除文件: {file_path}")
            except Exception as e:
                logging.error(f"删除文件 {file_path} 时发生错误: {e}")

def check_http_url(url, timeout):
    """检查 HTTP/HTTPS URL 是否活跃"""
    try:
        # 使用 requests.head 更高效地检查 URL 状态
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return 200 <= response.status_code < 400 # 2xx 成功，3xx 重定向也视为有效
    except requests.exceptions.RequestException as e:
        logging.debug(f"HTTP URL {url} 检查失败: {e}")
        return False

def check_rtmp_url(url, timeout):
    """使用 ffprobe 检查 RTMP 流是否可用"""
    try:
        # 检查 ffprobe 是否存在且工作
        subprocess.run(['ffprobe', '-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=2)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logging.warning("ffprobe 未找到或无法工作。RTMP 流无法检查。")
        return False
    try:
        # 使用 ffprobe 检查 RTMP 流
        result = subprocess.run(['ffprobe', '-v', 'error', '-rtmp_transport', 'tcp', '-i', url],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logging.debug(f"RTMP URL {url} 检查超时")
        return False
    except Exception as e:
        logging.debug(f"RTMP URL {url} 检查错误: {e}")
        return False

def check_rtp_url(url, timeout):
    """检查 RTP URL 是否活跃 (UDP协议)"""
    try:
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port
        if not host or not port:
            return False

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s: # UDP socket
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendto(b'', (host, port)) # 发送一个空数据包以尝试连接
            # 尝试接收数据，如果成功接收到数据，说明端口可达
            s.recv(1)
        return True
    except (socket.timeout, socket.error) as e:
        logging.debug(f"RTP URL {url} 检查失败: {e}")
        return False
    except Exception as e:
        logging.debug(f"RTP URL {url} 检查错误: {e}")
        return False

def check_p3p_url(url, timeout):
    """检查 P3P URL 是否活跃 (模拟HTTP请求)"""
    # 注意：P3P (Platform for Privacy Preferences Project) 并不是一个流媒体协议
    # 通常这是一个HTTP响应头，这里可能指的是特殊的HTTP服务
    # 模拟一个简单的HTTP GET请求来检查是否能连接和获取响应
    try:
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port if parsed_url.port else 80 # P3P通常是HTTP，默认端口80
        path = parsed_url.path if parsed_url.path else '/'

        if not host:
            return False

        with socket.create_connection((host, port), timeout=timeout) as s:
            request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: Python\r\n\r\n"
            s.sendall(request.encode())
            response = s.recv(1024).decode('utf-8', errors='ignore')
            # 检查响应头是否包含 P3P 字符串或 HTTP 成功状态码
            return "P3P" in response or response.startswith("HTTP/1.") # 检查HTTP响应是否成功
    except Exception as e:
        logging.debug(f"P3P URL {url} 检查失败: {e}")
        return False

def check_url_validity(url, channel_name, timeout=6):
    """根据协议检查URL的有效性"""
    start_time = time.time()
    success = False

    try:
        if url.startswith("http"):
            success = check_http_url(url, timeout)
        elif url.startswith("p3p"):
            success = check_p3p_url(url, timeout)
        elif url.startswith("rtmp"):
            success = check_rtmp_url(url, timeout)
        elif url.startswith("rtp"):
            success = check_rtp_url(url, timeout)
        else:
            logging.debug(f"不支持的协议 {channel_name}: {url}")
            return None, False

        elapsed_time = (time.time() - start_time) * 1000
        if success:
            return elapsed_time, True
        else:
            return None, False
    except Exception as e:
        logging.debug(f"检测频道 {channel_name} ({url}) 时发生错误: {e}")
        return None, False

def process_line(line):
    """处理单行频道数据，并进行有效性检查"""
    # 移除查询参数和片段，因为 clean_url_params 已经处理了
    # line = line.split('$')[0] # 原始脚本的逻辑，如果确定要只移除 $ 后面的内容，则保留此行
    if "://" not in line:
        return None, None
    parts = line.split(',', 1) # 只按第一个逗号分割
    if len(parts) == 2:
        name, url = parts
        url = url.strip() # 清理URL两边的空白
        elapsed_time, is_valid = check_url_validity(url, name)
        if is_valid:
            return elapsed_time, f"{name},{url}"
    return None, None

def process_urls_multithreaded(lines, max_workers=200):
    """多线程处理URL列表，进行有效性检查"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交任务时，传入完整的原始行
        futures = {executor.submit(process_line, line): line for line in lines}
        for future in as_completed(futures):
            # 即使任务失败，也捕获异常，避免程序中断
            try:
                elapsed_time, result_line = future.result()
                if elapsed_time is not None and result_line is not None:
                    results.append((elapsed_time, result_line))
            except Exception as exc:
                logging.warning(f"处理行时产生异常: {exc}")

    results.sort() # 按响应时间排序
    return results

def write_list(file_path, data_list):
    """将数据列表写入文件"""
    with open(file_path, 'w', encoding='utf-8') as file:
        for item in data_list:
            file.write(item[1] + '\n') # item[1] 是 'name,url' 格式的字符串

def sort_cctv_channels(channels):
    """对CCTV频道进行数字排序"""
    def channel_key(channel_line):
        channel_name_full = channel_line.split(',')[0].strip()
        match = re.search(r'\d+', channel_name_full)
        if match:
            return int(match.group())
        return float('inf') # 无法匹配数字的排在最后

    return sorted(channels, key=channel_key)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True, retry=retry_if_exception_type(requests.exceptions.RequestException))
def fetch_aggregator_url_with_retry(agg_url, timeout=20):
    """带重试机制地从聚合源获取内容"""
    logging.info(f"尝试从聚合源 {agg_url} 获取内容 (超时: {timeout}s)")
    response = requests.get(agg_url, timeout=timeout)
    response.raise_for_status()
    return response.text

def auto_discover_and_update_urls_file(config_urls_path, aggregator_urls_sources):
    logging.info("开始自动发现并更新 config/urls.txt 中的URLs...")
    discovered_urls = set()

    for agg_url in aggregator_urls_sources:
        try:
            content = fetch_aggregator_url_with_retry(agg_url)

            # 使用正则表达式发现URL
            found_by_regex = URL_PATTERN.findall(content)
            for match in found_by_regex:
                full_url = match if isinstance(match, str) else match[0]
                discovered_urls.add(full_url)
                logging.debug(f"Regex发现URL: {full_url}")

            # 使用 BeautifulSoup 解析 HTML 页面，发现更多URL
            if 'text/html' in requests.head(agg_url).headers.get('Content-Type', ''): # 检查是否是HTML内容
                soup = BeautifulSoup(content, 'html.parser')
                for code_tag in soup.find_all('code'): # 您的原始README.md中URL在<code>标签里
                    url = code_tag.get_text(strip=True)
                    if url.startswith("http://") or url.startswith("https://"):
                        discovered_urls.add(url)
                        logging.debug(f"HTML解析(code tag)发现URL: {url}")
                # 也可以查找 <a> 标签，根据您聚合源的实际情况
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    abs_url = urljoin(agg_url, href)
                    if URL_PATTERN.match(abs_url):
                        discovered_urls.add(abs_url)
                        logging.debug(f"HTML解析(a tag)发现URL: {abs_url}")

        except requests.exceptions.RequestException as e:
            logging.error(f"从聚合源 {agg_url} 抓取时发生HTTP请求错误（重试后失败）: {e}")
        except Exception as e:
            logging.error(f"从聚合源 {agg_url} 发现URLs时发生未知错误: {e}")

    verified_urls = set()
    logging.info(f"发现 {len(discovered_urls)} 个潜在URLs，开始验证内容...")

    # 验证发现的URL内容是否是有效的M3U/M3U8/TXT格式
    def verify_single_url_content(url):
        try:
            # 尝试获取URL内容的前几行，判断是否包含 M3U/M3U8/TXT 文件的特征
            # 使用 requests 替换 urllib.request
            response = requests.get(url, timeout=10, stream=True)
            response.raise_for_status()
            first_lines = ""
            for chunk in response.iter_content(chunk_size=1024):
                first_lines += chunk.decode('utf-8', errors='ignore')
                if len(first_lines) >= 1024:
                    break
            response.close() # 关闭连接

            if "#EXTM3U" in first_lines or re.search(r',https?://', first_lines): # 检查是否是M3U或频道列表格式
                return url
            return None
        except requests.exceptions.RequestException as e:
            logging.debug(f"验证URL内容失败 {url}: {e}")
            return None
        except Exception as e:
            logging.debug(f"验证URL内容时发生未知错误 {url}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(20, len(discovered_urls))) as executor:
        futures = [executor.submit(verify_single_url_content, url) for url in discovered_urls]
        for future in as_completed(futures):
            valid_url = future.result()
            if valid_url:
                verified_urls.add(valid_url)
                logging.debug(f"验证通过URL: {valid_url}")

    logging.info(f"通过内容验证的URLs数量: {len(verified_urls)}")

    existing_urls = set(read_txt_to_array(config_urls_path))
    initial_count = len(existing_urls)

    updated_urls = sorted(list(existing_urls.union(verified_urls)))

    try:
        with open(config_urls_path, 'w', encoding='utf-8') as f:
            for url in updated_urls:
                f.write(url + '\n')
        logging.info(f"config/urls.txt 已更新。新增URLs: {len(updated_urls) - initial_count} 条，总URLs: {len(updated_urls)} 条。")
    except Exception as e:
        logging.error(f"写入 config/urls.txt 时发生错误: {e}")


def main():
    config_dir = os.path.join(os.getcwd(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    urls_file_path = os.path.join(config_dir, 'urls.txt')

    # 1. 自动发现并更新 urls.txt
    auto_discover_and_update_urls_file(urls_file_path, AGGREGATOR_URLS)

    # 2. 从 urls.txt 读取需要处理的 URL 列表
    urls = read_txt_to_array(urls_file_path)
    if not urls:
        logging.warning("没有从 config/urls.txt 读取到任何URLs，脚本将提前退出。")
        return

    # 3. 处理所有聚合源中的频道列表
    all_channels = []
    # 使用线程池处理聚合源，提高效率
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                # future.result() 是一个生成器，需要迭代获取所有频道
                for name, addr in future.result():
                    all_channels.append((name, addr))
            except Exception as exc:
                logging.error(f"处理聚合源 {url} 时产生异常: {exc}")

    # 4. 过滤和清理频道名称
    filtered_channels = filter_and_modify_sources(all_channels)
    # 使用集合去重，然后转回列表
    unique_channels = list(set(filtered_channels))
    unique_channels_str = [f"{name},{url}" for name, url in unique_channels]

    iptv_file_path = os.path.join(os.getcwd(), 'iptv.txt')
    with open(iptv_file_path, 'w', encoding='utf-8') as f:
        for line in unique_channels_str:
            f.write(line + '\n')
    logging.info(f"\n所有频道已保存到文件: {iptv_file_path}，共采集到频道数量: {len(unique_channels_str)} 条\n")

    # 5. 多线程检查频道有效性和速度
    logging.info("开始多线程检查频道有效性和速度...")
    results = process_urls_multithreaded(unique_channels_str)
    logging.info(f"有效且响应的频道数量: {len(results)} 条")

    iptv_speed_file_path = os.path.join(os.getcwd(), 'iptv_speed.txt')
    write_list(iptv_speed_file_path, results)
    for elapsed_time, result in results:
        channel_name, channel_url = result.split(',', 1)
        logging.info(f"检测成功 {channel_name},{channel_url} 响应时间: {elapsed_time:.0f} 毫秒")

    # 6. 处理地方频道和模板
    local_channels_directory = os.path.join(os.getcwd(), '地方频道')
    os.makedirs(local_channels_directory, exist_ok=True)
    clear_txt_files(local_channels_directory) # 清理旧的TXT文件

    template_directory = os.path.join(os.getcwd(), '频道模板')
    os.makedirs(template_directory, exist_ok=True)
    template_files = [f for f in os.listdir(template_directory) if f.endswith('.txt')]

    iptv_speed_channels = read_txt_to_array(iptv_speed_file_path)

    all_template_channel_names = set()
    for template_file in template_files:
        names_from_current_template = read_txt_to_array(os.path.join(template_directory, template_file))
        all_template_channel_names.update(names_from_current_template)

    for template_file in template_files:
        template_channels_names = read_txt_to_array(os.path.join(template_directory, template_file))
        template_name = os.path.splitext(template_file)[0]

        current_template_matched_channels = []
        for channel_line in iptv_speed_channels:
            channel_name = channel_line.split(',', 1)[0].strip()
            if channel_name in template_channels_names:
                current_template_matched_channels.append(channel_line)

        if "央视" in template_name or "CCTV" in template_name:
            current_template_matched_channels = sort_cctv_channels(current_template_matched_channels)
            logging.info(f"已对 {template_name} 频道进行数字排序。")

        output_file_path = os.path.join(local_channels_directory, f"{template_name}_iptv.txt")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(f"{template_name},#genre#\n") # 写入分类头
            for channel in current_template_matched_channels:
                f.write(channel + '\n')
        logging.info(f"频道列表已写入: {template_name}_iptv.txt, 包含 {len(current_template_matched_channels)} 条频道。")

    # 7. 合并所有 IPTV 文件
    merge_iptv_files(local_channels_directory)

    # 8. 找出未匹配模板的频道
    unmatched_channels = []
    for channel_line in iptv_speed_channels:
        channel_name = channel_line.split(',', 1)[0].strip()
        if channel_name not in all_template_channel_names:
            unmatched_channels.append(channel_line)

    unmatched_output_file_path = os.path.join(os.getcwd(), 'unmatched_channels.txt')
    with open(unmatched_output_file_path, 'w', encoding='utf-8') as f:
        # 只写入频道名称
        for channel_line in unmatched_channels:
            f.write(channel_line.split(',')[0].strip() + '\n')
    logging.info(f"\n未匹配任何模板但检测成功的频道列表已保存到文件: {unmatched_output_file_path}，共 {len(unmatched_channels)} 条。")


if __name__ == "__main__":
    main()
