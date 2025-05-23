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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- GitHub API Configuration ---
GITHUB_API_BASE_URL = "https://api.github.com"
SEARCH_CODE_ENDPOINT = "/search/code"
# Retrieve GitHub Token from environment variable
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') # This variable will hold the token passed from GitHub Actions
# Search keywords for m3u/m3u8 files, optimized for broader search
SEARCH_KEYWORDS = [
    "m3u8 in:file extension:m3u8",
    "m3u in:file extension:m3u",
    "iptv playlist in:file extension:m3u,m3u8", # Common IPTV playlist keywords
    "raw.githubusercontent.com filename:.m3u8", # Explicitly search for raw.githubusercontent.com links
    "raw.githubusercontent.com filename:.m3u"
]
# Max results per page (GitHub API limit)
PER_PAGE = 100
# Limit total search pages to prevent excessive requests
MAX_SEARCH_PAGES = 5 # Increased to 5 pages for potentially more results

# --- Helper Functions ---

def read_txt_to_array(file_name):
    """Reads content from a TXT file, one element per line."""
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            lines = [line.strip() for line in lines if line.strip()]
            return lines
    except FileNotFoundError:
        logging.warning(f"File '{file_name}' not found. A new one will be created.")
        return []
    except Exception as e:
        logging.error(f"Error reading file '{file_name}': {e}")
        return []

def write_array_to_txt(file_name, data_array):
    """Writes array content to a TXT file, one element per line."""
    try:
        with open(file_name, 'w', encoding='utf-8') as file:
            for item in data_array:
                file.write(item + '\n')
        logging.info(f"Data successfully written to '{file_name}'.")
    except Exception as e:
        logging.error(f"Error writing file '{file_name}': {e}")

def get_url_file_extension(url):
    """Gets the file extension from a URL."""
    parsed_url = urlparse(url)
    extension = os.path.splitext(parsed_url.path)[1].lower()
    return extension

def convert_m3u_to_txt(m3u_content):
    """Converts m3u/m3u8 content to channel name and address in TXT format."""
    lines = m3u_content.split('\n')
    txt_lines = []
    channel_name = ""
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            match = re.search(r'#EXTINF:.*?\,(.*)', line)
            if match:
                channel_name = match.group(1).strip()
            else:
                channel_name = "Unknown Channel"
        elif line and not line.startswith('#'):
            if channel_name:
                txt_lines.append(f"{channel_name},{line}")
            channel_name = ""
    return '\n'.join(txt_lines)

def clean_url_params(url):
    """Cleans query parameters and fragment identifiers from a URL, keeping only the base URL."""
    parsed_url = urlparse(url)
    return parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True, retry=retry_if_exception_type(requests.exceptions.RequestException))
def fetch_url_content_with_retry(url, timeout=15):
    """Fetches URL content using requests with retries."""
    logging.info(f"Attempting to fetch URL: {url} (Timeout: {timeout}s)")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text

def process_url(url):
    """Processes a single URL, extracts channel names and addresses."""
    try:
        text = fetch_url_content_with_retry(url)

        if get_url_file_extension(url) in [".m3u", ".m3u8"]:
            text = convert_m3u_to_txt(text)

        lines = text.split('\n')
        channel_count = 0
        for line in lines:
            line = line.strip()
            if "#genre#" not in line and "," in line and "://" in line:
                parts = line.split(',', 1)
                channel_name = parts[0].strip()
                channel_address_raw = parts[1].strip()

                if '#' in channel_address_raw:
                    url_list = channel_address_raw.split('#')
                    for channel_url in url_list:
                        channel_url = clean_url_params(channel_url.strip())
                        if channel_url:
                            yield channel_name, channel_url
                            channel_count += 1
                else:
                    channel_url = clean_url_params(channel_address_raw)
                    if channel_url:
                        yield channel_name, channel_url
                        channel_count += 1
        logging.info(f"Successfully read URL: {url}, obtained {channel_count} channels.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error while processing URL (failed after retries): {url} - {e}")
    except Exception as e:
        logging.error(f"Unknown error while processing URL: {url} - {e}")

def filter_and_modify_sources(corrections):
    """Filters and modifies channel names and URLs."""
    filtered_corrections = []
    # Your filter lists remain unchanged
    name_dict = ['购物', '理财', '导视', '指南', '测试', '芒果', 'CGTN','(480p)','(360p)','(240p)','(406p)',' (540p)','(600p)','(576p)','[Not 24/7]','DJ','音乐','演唱会','舞曲','春晚','格斗','粤','祝','体育','广播','博斯','神话']
    url_dict = []

    for name, url in corrections:
        if any(word.lower() in name.lower() for word in name_dict) or \
           any(word in url for word in url_dict):
            logging.info(f"Filtering channel: {name},{url}")
        else:
            name = name.replace("FHD", "").replace("HD", "").replace("hd", "").replace("频道", "").replace("高清", "") \
                .replace("超清", "").replace("20M", "").replace("-", "").replace("4k", "").replace("4K", "") \
                .replace("4kR", "")
            filtered_corrections.append((name, url))
    return filtered_corrections

def clear_txt_files(directory):
    """Deletes all TXT files in the specified directory."""
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
                logging.info(f"Deleted file: {file_path}")
            except Exception as e:
                logging.error(f"Error deleting file {file_path}: {e}")

def check_http_url(url, timeout):
    """Checks if an HTTP/HTTPS URL is active."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return 200 <= response.status_code < 400
    except requests.exceptions.RequestException as e:
        logging.debug(f"HTTP URL {url} check failed: {e}")
        return False

def check_rtmp_url(url, timeout):
    """Checks if an RTMP stream is available using ffprobe."""
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
        logging.debug(f"RTMP URL {url} check timed out")
        return False
    except Exception as e:
        logging.debug(f"RTMP URL {url} check error: {e}")
        return False

def check_rtp_url(url, timeout):
    """Checks if an RTP URL is active (UDP protocol)."""
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
            s.recv(1) # Try to receive data
        return True
    except (socket.timeout, socket.error) as e:
        logging.debug(f"RTP URL {url} check failed: {e}")
        return False
    except Exception as e:
        logging.debug(f"RTP URL {url} check error: {e}")
        return False

def check_p3p_url(url, timeout):
    """Checks if a P3P URL is active (simulates an HTTP request)."""
    try:
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port if parsed_url.port else 80
        path = parsed_url.path if parsed_url.path else '/'

        if not host:
            return False

        with socket.create_connection((host, port), timeout=timeout) as s:
            request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: Python\r\n\r\n"
            s.sendall(request.encode())
            response = s.recv(1024).decode('utf-8', errors='ignore')
            return "P3P" in response or response.startswith("HTTP/1.")
    except Exception as e:
        logging.debug(f"P3P URL {url} check failed: {e}")
        return False

def check_url_validity(url, channel_name, timeout=6):
    """Checks the validity of a URL based on its protocol."""
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

        elapsed_time = (time.time() - start_time) * 1000
        if success:
            return elapsed_time, True
        else:
            return None, False
    except Exception as e:
        logging.debug(f"Error checking channel {channel_name} ({url}): {e}")
        return None, False

def process_line(line):
    """Processes a single channel line and checks validity."""
    if "://" not in line:
        return None, None
    parts = line.split(',', 1)
    if len(parts) == 2:
        name, url = parts
        url = url.strip()
        elapsed_time, is_valid = check_url_validity(url, name)
        if is_valid:
            return elapsed_time, f"{name},{url}"
    return None, None

def process_urls_multithreaded(lines, max_workers=200):
    """Processes a list of URLs concurrently for validity checking."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_line, line): line for line in lines}
        for future in as_completed(futures):
            try:
                elapsed_time, result_line = future.result()
                if elapsed_time is not None and result_line is not None:
                    results.append((elapsed_time, result_line))
            except Exception as exc:
                logging.warning(f"Exception during line processing: {exc}")

    results.sort()
    return results

def write_list(file_path, data_list):
    """Writes a list of data to a file."""
    with open(file_path, 'w', encoding='utf-8') as file:
        for item in data_list:
            file.write(item[1] + '\n')

def sort_cctv_channels(channels):
    """Sorts CCTV channels numerically."""
    def channel_key(channel_line):
        channel_name_full = channel_line.split(',')[0].strip()
        match = re.search(r'\d+', channel_name_full)
        if match:
            return int(match.group())
        return float('inf')

    return sorted(channels, key=channel_key)

def merge_iptv_files(local_channels_directory):
    """Merges all local channel files into iptv_list.txt."""
    final_output_lines = []
    
    now = datetime.now()
    update_time_line = [
        f"更新时间,#genre#\n",
        f"{now.strftime('%Y-%m-%d')},url\n",
        f"{now.strftime('%H:%M:%S')},url\n"
    ]
    final_output_lines.extend(update_time_line)

    ordered_categories = ["央视频道", "卫视频道", "湖南频道", "港台频道"]
    
    all_iptv_files_in_dir = [f for f in os.listdir(local_channels_directory) if f.endswith('_iptv.txt')]
    
    files_to_merge_paths = []
    processed_files = set()

    for category in ordered_categories:
        file_name = f"{category}_iptv.txt"
        if file_name in all_iptv_files_in_dir and file_name not in processed_files:
            files_to_merge_paths.append(os.path.join(local_channels_directory, file_name))
            processed_files.add(file_name)
    
    for file_name in sorted(all_iptv_files_in_dir):
        if file_name not in processed_files:
            files_to_merge_paths.append(os.path.join(local_channels_directory, file_name))
            processed_files.add(file_name)

    for file_path in files_to_merge_paths:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            if not lines:
                continue

            header = lines[0].strip()
            if '#genre#' in header:
                final_output_lines.append(header + '\n')
                
                grouped_channels_in_category = {}
                for line_content in lines[1:]:
                    line_content = line_content.strip()
                    if line_content:
                        channel_name = line_content.split(',', 1)[0].strip()
                        if channel_name not in grouped_channels_in_category:
                            grouped_channels_in_category[channel_name] = []
                        grouped_channels_in_category[channel_name].append(line_content)
                
                for channel_name in grouped_channels_in_category:
                    # Limit each channel to a maximum of 200 URLs to prevent excessively large files
                    for ch_line in grouped_channels_in_category[channel_name][:200]:
                        final_output_lines.append(ch_line + '\n')
            else:
                logging.warning(f"File {file_path} does not start with a category header. Skipping.")

    iptv_list_file_path = "iptv_list.txt"
    with open(iptv_list_file_path, "w", encoding="utf-8") as iptv_list_file:
        iptv_list_file.writelines(final_output_lines)

    try:
        # Delete temporary files
        if os.path.exists('iptv.txt'):
            os.remove('iptv.txt')
            logging.info(f"Temporary file iptv.txt deleted.")
        if os.path.exists('iptv_speed.txt'):
            os.remove('iptv_speed.txt')
            logging.info(f"Temporary file iptv_speed.txt deleted.")
    except OSError as e:
        logging.warning(f"Error deleting temporary files: {e}")

    logging.info(f"\nAll regional channel list files merged. Output saved to: {iptv_list_file_path}")


def auto_discover_github_urls(urls_file_path, github_token):
    """
    Automatically searches for public IPTV source URLs on GitHub and updates the urls.txt file.
    """
    if not github_token:
        logging.warning("GITHUB_TOKEN environment variable not set. Skipping GitHub URL auto-discovery.")
        return

    existing_urls = set(read_txt_to_array(urls_file_path))
    found_urls = set()
    headers = {
        "Accept": "application/vnd.github.v3.text-match+json",
        "Authorization": f"token {github_token}" # Ensure token is used here
    }

    logging.info("Starting auto-discovery of new IPTV source URLs from GitHub...")

    for keyword in SEARCH_KEYWORDS:
        page = 1
        while page <= MAX_SEARCH_PAGES:
            params = {
                "q": f"{keyword} in:path extension:m3u8,m3u", # Search in path and specific extensions
                "sort": "indexed", # Sort by indexed time (latest updates)
                "order": "desc",
                "per_page": PER_PAGE,
                "page": page
            }
            try:
                response = requests.get(
                    f"{GITHUB_API_BASE_URL}{SEARCH_CODE_ENDPOINT}",
                    headers=headers,
                    params=params,
                    timeout=20
                )
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                if not data.get('items'):
                    logging.info(f"No more results found for keyword '{keyword}' on page {page}.")
                    break

                for item in data['items']:
                    html_url = item.get('html_url', '')
                    raw_url = None
                    
                    # Attempt to construct raw.githubusercontent.com URL from html_url
                    # Matches typical GitHub blob URL format: https://github.com/<user>/<repo>/blob/<branch>/<path>
                    match = re.search(r'https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)', html_url)
                    
                    if match:
                        user = match.group(1)
                        repo = match.group(2)
                        branch = match.group(3)
                        path = match.group(4)
                        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
                    
                    if raw_url:
                        # Ensure the URL is a valid m3u/m3u8/txt URL AND originates from raw.githubusercontent.com
                        if raw_url.startswith("https://raw.githubusercontent.com/") and \
                           raw_url.lower().endswith(('.m3u', '.m3u8', '.txt')):
                            cleaned_url = clean_url_params(raw_url)
                            found_urls.add(cleaned_url)
                            logging.debug(f"Discovered raw GitHub URL: {cleaned_url}")
                        else:
                            logging.debug(f"Skipping non-raw GitHub M3U/M3U8/TXT link (does not match raw.githubusercontent.com or extension): {raw_url}")
                    else:
                        logging.debug(f"Could not construct raw URL from HTML URL: {html_url}")

                logging.info(f"Keyword '{keyword}', page {page} search completed. Currently found {len(found_urls)} raw URLs.")
                
                # Check if there are more pages by comparing item count with PER_PAGE
                if len(data['items']) < PER_PAGE:
                    break # Reached last page or no more results

                page += 1
                time.sleep(1) # Be polite, wait to avoid hitting rate limits

            except requests.exceptions.RequestException as e:
                logging.error(f"GitHub API request failed (Keyword: {keyword}, Page: {page}): {e}")
                # Check for rate limit error
                if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                    reset_time = int(response.headers['X-RateLimit-Reset'])
                    wait_seconds = max(0, reset_time - time.time()) + 5 # Wait 5 extra seconds
                    logging.warning(f"GitHub API rate limit hit! Waiting {wait_seconds:.0f} seconds before retrying/continuing.")
                    time.sleep(wait_seconds)
                else:
                    break # Break on other errors for this keyword
            except Exception as e:
                logging.error(f"Unknown error during GitHub URL auto-discovery: {e}")
                break # Break on unknown errors

    new_urls_count = 0
    for url in found_urls:
        if url not in existing_urls:
            existing_urls.add(url)
            new_urls_count += 1

    if new_urls_count > 0:
        updated_urls = list(existing_urls)
        write_array_to_txt(urls_file_path, updated_urls)
        logging.info(f"Successfully discovered and added {new_urls_count} new GitHub IPTV source URLs to {urls_file_path}. Total URLs: {len(updated_urls)}")
    else:
        logging.info("No new GitHub IPTV source URLs discovered.")

    logging.info("GitHub URL auto-discovery completed.")


def main():
    config_dir = os.path.join(os.getcwd(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    urls_file_path = os.path.join(config_dir, 'urls.txt')

    # --- START OF NEW DEBUG LOGGING ---
    # This will check if the GITHUB_TOKEN environment variable is set
    if os.getenv('GITHUB_TOKEN'):
        logging.info("Environment variable 'GITHUB_TOKEN' IS SET.")
    else:
        logging.error("Environment variable 'GITHUB_TOKEN' IS NOT SET! Please check GitHub Actions workflow configuration.")
    # --- END OF NEW DEBUG LOGGING ---

    # 1. Automatically discover GitHub URLs and update urls.txt
    # Ensure GITHUB_TOKEN is passed from GitHub Actions (e.g., using secrets.BOT)
    auto_discover_github_urls(urls_file_path, GITHUB_TOKEN)

    # 2. Read URLs to process from urls.txt (including newly discovered ones)
    urls = read_txt_to_array(urls_file_path)
    if not urls:
        logging.warning(f"No URLs found in {urls_file_path}, script will exit early.")
        return

    # 3. Process all channel lists from config/urls.txt
    all_channels = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                for name, addr in future.result():
                    all_channels.append((name, addr))
            except Exception as exc:
                logging.error(f"Exception processing source {url}: {exc}")

    # 4. Filter and clean channel names
    filtered_channels = filter_and_modify_sources(all_channels)
    unique_channels = list(set(filtered_channels))
    unique_channels_str = [f"{name},{url}" for name, url in unique_channels]

    iptv_file_path = os.path.join(os.getcwd(), 'iptv.txt')
    with open(iptv_file_path, 'w', encoding='utf-8') as f:
        for line in unique_channels_str:
            f.write(line + '\n')
    logging.info(f"\nAll channels saved to: {iptv_file_path}, total channels collected: {len(unique_channels_str)}\n")

    # 5. Multi-threaded channel validity and speed check
    logging.info("Starting multi-threaded channel validity and speed check...")
    results = process_urls_multithreaded(unique_channels_str)
    logging.info(f"Number of valid and responsive channels: {len(results)}")

    iptv_speed_file_path = os.path.join(os.getcwd(), 'iptv_speed.txt')
    write_list(iptv_speed_file_path, results)
    for elapsed_time, result in results:
        channel_name, channel_url = result.split(',', 1)
        logging.info(f"Check successful for {channel_name},{channel_url} Response time: {elapsed_time:.0f} ms")

    # 6. Process regional channels and templates
    local_channels_directory = os.path.join(os.getcwd(), '地方频道')
    os.makedirs(local_channels_directory, exist_ok=True)
    clear_txt_files(local_channels_directory)

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
            logging.info(f"Sorted {template_name} channels numerically.")

        output_file_path = os.path.join(local_channels_directory, f"{template_name}_iptv.txt")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(f"{template_name},#genre#\n")
            for channel in current_template_matched_channels:
                f.write(channel + '\n')
        logging.info(f"Channel list written to: {template_name}_iptv.txt, containing {len(current_template_matched_channels)} channels.")

    # 7. Merge all IPTV files
    merge_iptv_files(local_channels_directory)

    # 8. Find unmatched channels
    unmatched_channels = []
    for channel_line in iptv_speed_channels:
        channel_name = channel_line.split(',', 1)[0].strip()
        if channel_name not in all_template_channel_names:
            unmatched_channels.append(channel_line)

    unmatched_output_file_path = os.path.join(os.getcwd(), 'unmatched_channels.txt')
    with open(unmatched_output_file_path, 'w', encoding='utf-8') as f:
        for channel_line in unmatched_channels:
            f.write(channel_line.split(',')[0].strip() + '\n')
    logging.info(f"\nList of unmatched but detected channels saved to: {unmatched_output_file_path}, total {len(unmatched_channels)} channels.")


if __name__ == "__main__":
    main()
