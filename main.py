import urllib.request
from urllib.parse import urlparse, urljoin
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import socket
import time
from datetime import datetime
import logging
import requests # Added for web fetching
from bs4 import BeautifulSoup # Added for HTML parsing

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 自动URLs抓取配置 ---
# 这里放置你认为可能包含其他IPTV源列表链接的聚合页或GitHub README的URL
# 示例：一个著名的IPTV项目GitHub仓库的README.md原始链接
# 请替换为实际的，可能会包含更多源列表URL的聚合页
AGGREGATOR_URLS = [
    "https://raw.githubusercontent.com/iptv-org/iptv/master/README.md", # 示例：GitHub项目的README
    # "https://www.example.com/some_iptv_list_aggregator_page.html" # 另一个假设的聚合网页
]

# 用于在抓取到的内容中识别URLs的正则表达式（更宽泛）
# 匹配以 http/https 开头，以 .m3u, .m3u8, .txt 结尾的URL
URL_PATTERN = re.compile(r'https?://[^\s"<>()]*?\.(m3u|m3u8|txt)(?:\?.*?)?(?:#[^\s"<>]*?)?')
# --- 自动URLs抓取配置结束 ---


# 读取文本方法
def read_txt_to_array(file_name):
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            lines = [line.strip() for line in lines if line.strip()] # Filter out empty lines
            return lines
    except FileNotFoundError:
        logging.error(f"File '{file_name}' not found.")
        return []
    except Exception as e:
        logging.error(f"An error occurred reading '{file_name}': {e}")
        return []

# 准备支持 m3u 格式
def get_url_file_extension(url):
    parsed_url = urlparse(url)
    extension = os.path.splitext(parsed_url.path)[1]
    return extension

def convert_m3u_to_txt(m3u_content):
    lines = m3u_content.split('\n')
    txt_lines = []
    channel_name = ""
    for line in lines:
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            channel_name = line.split(',')[-1].strip()
        elif line.startswith("http") or line.startswith("rtmp") or line.startswith("p3p"):
            txt_lines.append(f"{channel_name},{line.strip()}")
    return '\n'.join(txt_lines)


# 处理带 $ 的 URL，把 $ 之后的内容都去掉（包括 $ 也去掉）
def clean_url_params(url): # Renamed to avoid confusion with the main 'clean_url' concept earlier
    last_dollar_index = url.rfind('$')
    if last_dollar_index != -1:
        return url[:last_dollar_index]
    return url


# 处理所有 URL (不变)
def process_url(url, timeout=10):
    try:
        start_time = time.time()
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read()
            text = data.decode('utf-8')

            if get_url_file_extension(url) == ".m3u" or get_url_file_extension(url) == ".m3u8":
                text = convert_m3u_to_txt(text)

            lines = text.split('\n')
            channel_count = 0
            for line in lines:
                if "#genre#" not in line and "," in line and "://" in line:
                    parts = line.split(',')
                    channel_name = parts[0].strip()
                    channel_address = parts[1].strip()
                    if "#" not in channel_address:
                        yield channel_name, clean_url_params(channel_address)
                    else:
                        url_list = channel_address.split('#')
                        for channel_url in url_list:
                            yield channel_name, clean_url_params(channel_url)
                    channel_count += 1

            logging.info(f"正在读取URL: {url}")
            logging.info(f"获取到频道列表: {channel_count} 条")

    except Exception as e:
        logging.error(f"处理 URL 时发生错误：{e}")
        return []


# 函数用于过滤和替换频道名称 (不变)
def filter_and_modify_sources(corrections):
    filtered_corrections = []
    name_dict = ['购物', '理财', '导视', '指南', '测试', '芒果', 'CGTN']
    url_dict = []  # '2409:'留空不过滤ipv6频道

    for name, url in corrections:
        if any(word.lower() in name.lower() for word in name_dict) or any(word in url for word in url_dict):
            logging.info("过滤频道:" + name + "," + url)
        else:
            name = name.replace("FHD", "").replace("HD", "").replace("hd", "").replace("频道", "").replace("高清", "") \
                .replace("超清", "").replace("20M", "").replace("-", "").replace("4k", "").replace("4K", "") \
                .replace("4kR", "")
            filtered_corrections.append((name, url))
    return filtered_corrections


# 删除目录内所有 .txt 文件 (不变)
def clear_txt_files(directory):
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
            except Exception as e:
                logging.error(f"删除文件时发生错误: {e}")

# 以下是检测不同协议URL的函数 (不变)
def check_http_url(url, timeout):
    try:
        # Using requests for HTTP checks can be more robust than urllib
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logging.debug(f"HTTP check failed for {url}: {e}")
        return False

def check_rtmp_url(url, timeout):
    try:
        subprocess.run(['ffprobe', '-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=2)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logging.warning("ffprobe not found or not working. RTMP streams cannot be checked.")
        return False
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-rtmp_transport', 'tcp', '-i', url],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, timeout=timeout)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logging.debug(f"RTMP check timed out for {url}")
        return False
    except Exception as e:
        logging.debug(f"RTMP check error for {url}: {e}")
        return False

def check_rtp_url(url, timeout):
    try:
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port
        if not host or not port:
            return False

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendto(b'', (host, port))
            s.recv(1)
        return True
    except (socket.timeout, socket.error) as e:
        logging.debug(f"RTP check failed for {url}: {e}")
        return False

def check_p3p_url(url, timeout):
    try:
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port
        path = parsed_url.path
        if not host or not port:
            return False

        with socket.create_connection((host, port), timeout=timeout) as s:
            request = f"GET {path} P3P/1.0\r\nHost: {host}\r\n\r\n"
            s.sendall(request.encode())
            response = s.recv(1024)
            return b"P3P" in response
    except Exception as e:
        logging.debug(f"P3P check failed for {url}: {e}")
        return False

def check_url_validity(url, channel_name, timeout=6): # Renamed to avoid clash with main check_url
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
            logging.debug(f"Unsupported protocol for {channel_name}: {url}")
            return None, False

        elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
        if success:
            return elapsed_time, True
        else:
            return None, False
    except Exception as e:
        logging.debug(f"检测错误 {channel_name}: {url}: {e}")
        return None, False

# 去掉文本'$'后面的内容 (不变)
def process_line(line):
    if "://" not in line:
        return None, None
    line = line.split('$')[0]
    parts = line.split(',')
    if len(parts) == 2:
        name, url = parts
        # check_url_validity returns (elapsed_time, success_boolean)
        elapsed_time, is_valid = check_url_validity(url.strip(), name)
        if is_valid:
            return elapsed_time, f"{name},{url}"
    return None, None

def process_urls_multithreaded(lines, max_workers=200):
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_line, line): line for line in lines}
        for future in as_completed(futures):
            elapsed_time, result = future.result()
            if elapsed_time is not None and result is not None:
                results.append((elapsed_time, result))

    # 按照检测后的毫秒数升序排列
    results.sort()
    return results

# 写入文件 (不变)
def write_list(file_path, data_list):
    with open(file_path, 'w', encoding='utf-8') as file:
        for item in data_list:
            # item is (elapsed_time, "channel_name,channel_url")
            file.write(item[1] + '\n')

def sort_cctv_channels(channels):
    """Sorts CCTV channels numerically."""
    def channel_key(channel_name_full):
        channel_name = channel_name_full.split(',')[0]
        match = re.search(r'\d+', channel_name)
        if match:
            return int(match.group())
        return float('inf')

    return sorted(channels, key=channel_key)


def merge_iptv_files(local_channels_directory):
    final_output_lines = []
    
    # Add update time at the beginning
    now = datetime.now()
    update_time_line = [
        f"更新时间,#genre#\n",
        f"{now.strftime('%Y-%m-%d')},url\n",
        f"{now.strftime('%H:%M:%S')},url\n"
    ]
    final_output_lines.extend(update_time_line)

    # Define preferred order for categories
    ordered_categories = ["央视频道", "卫视频道", "湖南频道", "港台频道"]
    
    # Get all _iptv.txt files from local_channels_directory
    all_iptv_files_in_dir = [f for f in os.listdir(local_channels_directory) if f.endswith('_iptv.txt')]
    
    # Prepare ordered list of file paths
    files_to_merge_paths = []
    processed_files = set()

    for category in ordered_categories:
        file_name = f"{category}_iptv.txt"
        if file_name in all_iptv_files_in_dir and file_name not in processed_files:
            files_to_merge_paths.append(os.path.join(local_channels_directory, file_name))
            processed_files.add(file_name)
    
    # Add remaining files alphabetically
    for file_name in sorted(all_iptv_files_in_dir):
        if file_name not in processed_files:
            files_to_merge_paths.append(os.path.join(local_channels_directory, file_name))
            processed_files.add(file_name)

    # Process files to merge, adding genre headers and limiting channels per name
    for file_path in files_to_merge_paths:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            if not lines:
                continue

            header = lines[0].strip()
            if '#genre#' in header:
                final_output_lines.append(header + '\n')
                
                # Group channels within this category by channel name
                grouped_channels_in_category = {}
                for line_content in lines[1:]: # Skip header
                    line_content = line_content.strip()
                    if line_content:
                        channel_name = line_content.split(',', 1)[0].strip()
                        if channel_name not in grouped_channels_in_category:
                            grouped_channels_in_category[channel_name] = []
                        grouped_channels_in_category[channel_name].append(line_content)
                
                # Add channels for this category, applying the 200 limit per channel name group
                for channel_name in grouped_channels_in_category:
                    for ch_line in grouped_channels_in_category[channel_name][:200]:
                        final_output_lines.append(ch_line + '\n')
            else:
                # Should not happen if all category files are correctly formatted
                logging.warning(f"File {file_path} does not start with a genre header. Skipping.")

    iptv_list_file_path = "iptv_list.txt"
    with open(iptv_list_file_path, "w", encoding="utf-8") as iptv_list_file:
        iptv_list_file.writelines(final_output_lines)

    try:
        os.remove('iptv.txt')
        os.remove('iptv_speed.txt')
        logging.info(f"临时文件 iptv.txt 和 iptv_speed.txt 已删除。")
    except OSError as e:
        logging.warning(f"删除临时文件时发生错误: {e}")

    logging.info(f"\n所有地区频道列表文件合并完成，文件保存为：{iptv_list_file_path}")


# --- 新增函数：自动发现URLs并更新config/urls.txt ---
def auto_discover_and_update_urls_file(config_urls_path, aggregator_urls_sources):
    logging.info("开始自动发现并更新 config/urls.txt 中的URLs...")
    discovered_urls = set()

    for agg_url in aggregator_urls_sources:
        try:
            logging.info(f"尝试从聚合源 {agg_url} 发现URLs...")
            response = requests.get(agg_url, timeout=20)
            response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            
            content = response.text
            
            # 1. 使用正则表达式查找潜在的URLs
            found_by_regex = URL_PATTERN.findall(content)
            for match in found_by_regex:
                # regex.findall returns a tuple if groups are used, take the whole match
                full_url = match if isinstance(match, str) else match[0] # Take the full URL if regex group is used
                discovered_urls.add(full_url)
                logging.debug(f"Regex发现URL: {full_url}")

            # 2. 如果是HTML内容，使用BeautifulSoup解析<a>标签的href属性
            if 'text/html' in response.headers.get('Content-Type', ''):
                soup = BeautifulSoup(content, 'html.parser')
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    # 组合相对URL为绝对URL
                    abs_url = urljoin(agg_url, href)
                    # 再次检查URL模式
                    if URL_PATTERN.match(abs_url):
                        discovered_urls.add(abs_url)
                        logging.debug(f"HTML解析发现URL: {abs_url}")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"从聚合源 {agg_url} 抓取时发生HTTP请求错误: {e}")
        except Exception as e:
            logging.error(f"从聚合源 {agg_url} 发现URLs时发生未知错误: {e}")

    # 验证发现的URLs是否是有效的IPTV列表（可以根据需要调整验证的严格性）
    verified_urls = set()
    logging.info(f"发现 {len(discovered_urls)} 个潜在URLs，开始验证...")
    # 可以使用ThreadPoolExecutor加速验证过程
    def verify_single_url_content(url):
        try:
            with urllib.request.urlopen(url, timeout=10) as res:
                # 读取前几行进行判断，避免下载整个大文件
                first_lines = res.read(1024).decode('utf-8', errors='ignore') # Read first 1KB
                # 判断是否包含M3U或普通txt列表的特征
                if "#EXTM3U" in first_lines or re.search(r',https?://', first_lines):
                    return url
            return None
        except Exception as e:
            logging.debug(f"验证URL内容失败 {url}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(20, len(discovered_urls))) as executor:
        futures = [executor.submit(verify_single_url_content, url) for url in discovered_urls]
        for future in as_completed(futures):
            valid_url = future.result()
            if valid_url:
                verified_urls.add(valid_url)
                logging.debug(f"验证通过URL: {valid_url}")

    logging.info(f"通过验证的URLs数量: {len(verified_urls)}")

    # 读取现有的URLs
    existing_urls = set(read_txt_to_array(config_urls_path))
    initial_count = len(existing_urls)

    # 合并新的URLs，并去重
    updated_urls = sorted(list(existing_urls.union(verified_urls)))
    
    # 写入更新后的URLs到文件
    try:
        with open(config_urls_path, 'w', encoding='utf-8') as f:
            for url in updated_urls:
                f.write(url + '\n')
        logging.info(f"config/urls.txt 已更新。新增URLs: {len(updated_urls) - initial_count} 条，总URLs: {len(updated_urls)} 条。")
    except Exception as e:
        logging.error(f"写入 config/urls.txt 时发生错误: {e}")


# --- 主函数 ---
def main():
    config_dir = os.path.join(os.getcwd(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    urls_file_path = os.path.join(config_dir, 'urls.txt')

    # --- 调用自动发现URLs函数 ---
    auto_discover_and_update_urls_file(urls_file_path, AGGREGATOR_URLS)
    # --- 调用结束 ---

    urls = read_txt_to_array(urls_file_path)
    if not urls:
        logging.warning("没有从 config/urls.txt 读取到任何URLs，脚本将提前退出。")
        return

    all_channels = []
    for url in urls:
        for channel_name, channel_url in process_url(url):
            all_channels.append((channel_name, channel_url))

    filtered_channels = filter_and_modify_sources(all_channels)
    unique_channels = list(set(filtered_channels))
    unique_channels_str = [f"{name},{url}" for name, url in unique_channels]

    iptv_file_path = os.path.join(os.getcwd(), 'iptv.txt')
    with open(iptv_file_path, 'w', encoding='utf-8') as f:
        for line in unique_channels_str:
            f.write(line + '\n')
    logging.info(f"\n所有频道已保存到文件: {iptv_file_path}，共采集到频道数量: {len(unique_channels_str)} 条\n")

    results = process_urls_multithreaded(unique_channels_str)

    iptv_speed_file_path = os.path.join(os.getcwd(), 'iptv_speed.txt')
    write_list(iptv_speed_file_path, results)

    # Note: These INFO logs are for all successful checks, not necessarily what ends up in iptv_list.txt
    for elapsed_time, result in results:
        channel_name, channel_url = result.split(',', 1)
        logging.info(f"检测成功  {channel_name},{channel_url}  响应时间 ：{elapsed_time:.0f} 毫秒")

    local_channels_directory = os.path.join(os.getcwd(), '地方频道')
    os.makedirs(local_channels_directory, exist_ok=True)
    clear_txt_files(local_channels_directory)

    template_directory = os.path.join(os.getcwd(), '频道模板')
    os.makedirs(template_directory, exist_ok=True)
    template_files = [f for f in os.listdir(template_directory) if f.endswith('.txt')]

    iptv_speed_channels = read_txt_to_array(iptv_speed_file_path)

    # Collect all channel names from templates
    all_template_channel_names = set()
    for template_file in template_files:
        names_from_current_template = read_txt_to_array(os.path.join(template_directory, template_file))
        all_template_channel_names.update(names_from_current_template) # Add all names to the set

    # Process channels based on templates
    matched_channels_in_templates = set() # To store channel lines (name,url) that matched a template
    for template_file in template_files:
        template_channels_names = read_txt_to_array(os.path.join(template_directory, template_file))
        template_name = os.path.splitext(template_file)[0]

        current_template_matched_channels = []
        for channel_line in iptv_speed_channels:
            channel_name = channel_line.split(',')[0].strip()
            if channel_name in template_channels_names:
                current_template_matched_channels.append(channel_line)
                matched_channels_in_templates.add(channel_line) # Add to the set of matched channels

        if "央视" in template_name or "CCTV" in template_name:
            current_template_matched_channels = sort_cctv_channels(current_template_matched_channels)
            logging.info(f"已对 {template_name} 频道进行数字排序。")

        output_file_path = os.path.join(local_channels_directory, f"{template_name}_iptv.txt")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(f"{template_name},#genre#\n")
            for channel in current_template_matched_channels:
                f.write(channel + '\n')
        logging.info(f"频道列表已写入: {template_name}_iptv.txt, 包含 {len(current_template_matched_channels)} 条频道。")

    merge_iptv_files(local_channels_directory)


    ## 输出未匹配模板的频道列表


    # Find channels that are in iptv_speed_channels but NOT in any template
    unmatched_channels = []
    for channel_line in iptv_speed_channels:
        channel_name = channel_line.split(',')[0].strip()
        if channel_name not in all_template_channel_names:
            unmatched_channels.append(channel_line)


  
    unmatched_output_file_path = os.path.join(os.getcwd(), 'unmatched_channels.txt')
    with open(unmatched_output_file_path, 'w', encoding='utf-8') as f:
        for channel_line in unmatched_channels:
            # Only write the channel name as requested
            f.write(channel_line.split(',')[0].strip() + '\n') 
    logging.info(f"\n未匹配任何模板但检测成功的频道列表已保存到文件: {unmatched_output_file_path}，共 {len(unmatched_channels)} 条。")

   

if __name__ == "__main__":
    main()
