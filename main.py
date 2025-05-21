import urllib.request
from urllib.parse import urlparse
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import socket
import time
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions (as provided, with minor tweaks) ---
def read_txt_to_array(file_name):
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            return [line.strip() for line in lines]
    except FileNotFoundError:
        logging.error(f"File '{file_name}' not found.")
        return []
    except Exception as e:
        logging.error(f"An error occurred reading '{file_name}': {e}")
        return []

def get_url_file_extension(url):
    parsed_url = urlparse(url)
    return os.path.splitext(parsed_url.path)[1]

def convert_m3u_to_txt(m3u_content):
    lines = m3u_content.split('\n')
    txt_lines = []
    channel_name = ""
    for line in lines:
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            channel_name = line.split(',')[-1].strip()
        elif line.startswith(("http", "rtmp", "p3p")):
            txt_lines.append(f"{channel_name},{line.strip()}")
    return '\n'.join(txt_lines)

def clean_url_params(url):
    # Remove everything after the last '$'
    last_dollar_index = url.rfind('$')
    if last_dollar_index != -1:
        return url[:last_dollar_index]
    return url

def process_single_url_source(url, timeout=10):
    """Fetches and parses channels from a given URL."""
    try:
        logging.info(f"Processing URL: {url}")
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read()
            text = data.decode('utf-8')

            if get_url_file_extension(url) in (".m3u", ".m3u8"):
                text = convert_m3u_to_txt(text)

            channels = []
            for line in text.split('\n'):
                if "#genre#" not in line and "," in line and "://" in line:
                    parts = line.split(',')
                    channel_name = parts[0].strip()
                    channel_address_raw = parts[1].strip()

                    # Handle multiple URLs separated by '#'
                    if "#" in channel_address_raw:
                        url_list = channel_address_raw.split('#')
                        for sub_url in url_list:
                            channels.append((channel_name, clean_url_params(sub_url)))
                    else:
                        channels.append((channel_name, clean_url_params(channel_address_raw)))
            logging.info(f"Found {len(channels)} channels from {url}")
            return channels
    except Exception as e:
        logging.error(f"Error processing URL {url}: {e}")
        return []

def filter_and_modify_channels(channels_list):
    """Filters channels based on name/URL blacklists and cleans names."""
    filtered_channels = []
    # These could come from a config file
    name_blacklist = ['购物', '理财', '导视', '指南', '测试', '芒果', 'CGTN']
    url_blacklist = [] # '2409:' for IPv6 example

    for name, url in channels_list:
        if any(word.lower() in name.lower() for word in name_blacklist) or \
           any(word in url for word in url_blacklist):
            logging.info(f"Filtering channel: {name},{url}")
        else:
            # More efficient name cleaning using regex
            name = re.sub(r'(FHD|HD|hd|频道|高清|超清|20M|-|4k|4K|4kR)', '', name, flags=re.IGNORECASE).strip()
            filtered_channels.append((name, url))
    return filtered_channels

def clear_txt_files(directory):
    """Deletes all .txt files in a given directory."""
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
                logging.info(f"Deleted old file: {file_path}")
            except Exception as e:
                logging.error(f"Error deleting file {file_path}: {e}")

# --- URL Health Check Functions ---
def check_http_url(url, timeout):
    try:
        response = urllib.request.urlopen(url, timeout=timeout)
        return response.status == 200
    except Exception as e:
        logging.debug(f"HTTP check failed for {url}: {e}")
        return False

def check_rtmp_url(url, timeout):
    try:
        # Check if ffprobe is available
        subprocess.run(['ffprobe', '-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning("ffprobe not found. RTMP streams cannot be checked.")
        return False
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-rtmp_transport', 'tcp', '-i', url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )
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
            s.sendto(b'', (host, port)) # Send a dummy packet
            s.recv(1) # Try to receive a response
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

def check_channel_url(channel_info, timeout=6):
    """Checks the validity and response time of a channel URL."""
    channel_name, url = channel_info
    start_time = time.time()
    is_valid = False
    
    try:
        if url.startswith("http"):
            is_valid = check_http_url(url, timeout)
        elif url.startswith("p3p"):
            is_valid = check_p3p_url(url, timeout)
        elif url.startswith("rtmp"):
            is_valid = check_rtmp_url(url, timeout)
        elif url.startswith("rtp"):
            is_valid = check_rtp_url(url, timeout)
        else:
            logging.debug(f"Unsupported protocol for {url}")
            return None, False

        elapsed_time = (time.time() - start_time) * 1000 # Milliseconds
        if is_valid:
            logging.info(f"Checked success: {channel_name},{url} - {elapsed_time:.0f} ms")
            return elapsed_time, f"{channel_name},{url}"
        else:
            logging.debug(f"Check failed for {channel_name},{url}")
            return None, False
    except Exception as e:
        logging.error(f"Error during check for {channel_name}, {url}: {e}")
        return None, False

def validate_channels_multithreaded(channels, max_workers=200):
    """Validates a list of (name, url) tuples using multiple threads."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Pass a tuple (name, url) to the worker function
        futures = {executor.submit(check_channel_url, channel): channel for channel in channels}
        for future in as_completed(futures):
            elapsed_time, result_str = future.result()
            if result_str: # result_str will be None if check failed
                results.append((elapsed_time, result_str))
    
    results.sort(key=lambda x: x[0]) # Sort by elapsed time
    return results

def write_channels_to_file(file_path, data_list):
    """Writes a list of (elapsed_time, channel_string) tuples to a file."""
    with open(file_path, 'w', encoding='utf-8') as file:
        for elapsed_time, channel_str in data_list:
            file.write(channel_str + '\n')
    logging.info(f"Channels written to {file_path}")

def sort_cctv_channels(channels):
    """Sorts CCTV channels numerically."""
    def channel_key(channel_name_full):
        # Extract just the channel name part before the comma for sorting
        channel_name = channel_name_full.split(',')[0]
        match = re.search(r'\d+', channel_name)
        if match:
            return int(match.group())
        return float('inf') # Non-numeric names go to the end
    
    # Sort the list of channel strings directly
    return sorted(channels, key=channel_key)

def merge_and_finalize_iptv_list(local_channels_directory, final_output_file="iptv_list.txt"):
    """Merges sorted IPTV files into a final list."""
    merged_content_lines = []
    
    # Define preferred order for categories
    ordered_categories = ["央视频道", "卫视频道", "湖南频道", "港台频道"]
    
    # Get all _iptv.txt files, excluding those in ordered_categories for now
    all_iptv_files = [f for f in os.listdir(local_channels_directory) if f.endswith('_iptv.txt')]
    
    # Process ordered categories first
    for category in ordered_categories:
        file_name = f"{category}_iptv.txt"
        if file_name in all_iptv_files:
            file_path = os.path.join(local_channels_directory, file_name)
            with open(file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()
                if lines: # Add category header and content if file is not empty
                    merged_content_lines.extend(lines)
            all_iptv_files.remove(file_name)

    # Add remaining categories alphabetically
    for file_name in sorted(all_iptv_files):
        file_path = os.path.join(local_channels_directory, file_name)
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            if lines:
                merged_content_lines.extend(lines)

    # Add update time
    now = datetime.now()
    update_time_lines = [
        f"更新时间,#genre#\n",
        f"{now.strftime('%Y-%m-%d')},url\n",
        f"{now.strftime('%H:%M:%S')},url\n"
    ]

    # Group channels by name and limit to top N (e.g., 200)
    channels_grouped = {}
    for line in merged_content_lines:
        line = line.strip()
        if line and '#genre#' not in line: # Exclude genre lines from grouping
            parts = line.split(',', 1) # Split only on the first comma
            if len(parts) == 2:
                channel_name = parts[0].strip()
                if channel_name not in channels_grouped:
                    channels_grouped[channel_name] = []
                # Add the full line, ensuring it's exactly as intended for output
                channels_grouped[channel_name].append(line + '\n')

    final_output_lines = []
    final_output_lines.extend(update_time_lines) # Add update time at the beginning

    # Re-add genre headers before their respective channel blocks
    # This requires re-reading the categories or managing them alongside
    # For simplicity, we'll re-iterate ordered categories for headers
    # A more robust solution might pass the original 'template_name' along

    # This part requires careful reconstruction to maintain genre headers.
    # A better approach might be to build `merged_content_lines` with genre headers already in place
    # and then process for max_channels_per_group.

    # For now, let's just write the grouped channels after the update time.
    # You might want to reconstruct genre headers explicitly here if desired.
    for category in ordered_categories:
        file_name = f"{category}_iptv.txt"
        file_path = os.path.join(local_channels_directory, file_name)
        if os.path.exists(file_path):
             with open(file_path, "r", encoding="utf-8") as file:
                 lines = file.readlines()
                 genre_header = ""
                 channels_for_category = []
                 for line in lines:
                     if '#genre#' in line:
                         genre_header = line
                     else:
                         channels_for_category.append(line.strip())
                 
                 if genre_header:
                     final_output_lines.append(genre_header)
                 
                 processed_count = 0
                 for channel_line in channels_for_category:
                     name = channel_line.split(',', 1)[0]
                     if name in channels_grouped and processed_count < 200:
                         # Append the actual channel line, not just its name
                         final_output_lines.append(channel_line + '\n')
                         processed_count += 1
                         
    # For remaining categories (not in ordered_categories)
    # This part needs to be carefully aligned with the initial file merging
    # The current grouping logic assumes unique channel names across all files,
    # which might not be what you want for genre separation.

    # A more robust approach for merging and grouping:
    # 1. Collect all channels with their original genre context.
    # 2. Validate all channels.
    # 3. Then, for each genre, apply sorting and grouping, then write.
    # This avoids the complex "reconstruction" of headers.

    # Let's simplify the final merge step for demonstration:
    # Assuming `merged_content_lines` now contains all lines (including genre headers)
    # in the desired order after initial merging.
    
    final_combined_output = []
    final_combined_output.extend(update_time_lines)

    current_genre_lines = []
    current_channels_in_genre = []
    
    for line in merged_content_lines:
        line = line.strip()
        if '#genre#' in line:
            # Process previous genre's channels before adding new genre header
            if current_genre_lines:
                final_combined_output.extend(current_genre_lines)
                
                # Apply grouping/limiting for this genre's channels
                genre_channels_grouped = {}
                for ch_line in current_channels_in_genre:
                    ch_name = ch_line.split(',',1)[0].strip()
                    if ch_name not in genre_channels_grouped:
                        genre_channels_grouped[ch_name] = []
                    genre_channels_grouped[ch_name].append(ch_line + '\n')

                for ch_name in genre_channels_grouped:
                    for processed_line in genre_channels_grouped[ch_name][:200]:
                        final_combined_output.append(processed_line)

            current_genre_lines = [line + '\n']
            current_channels_in_genre = []
        elif line: # Regular channel line
            current_channels_in_genre.append(line)
    
    # Process the last genre's channels
    if current_genre_lines:
        final_combined_output.extend(current_genre_lines)
        genre_channels_grouped = {}
        for ch_line in current_channels_in_genre:
            ch_name = ch_line.split(',',1)[0].strip()
            if ch_name not in genre_channels_grouped:
                genre_channels_grouped[ch_name] = []
            genre_channels_grouped[ch_name].append(ch_line + '\n')
        for ch_name in genre_channels_grouped:
            for processed_line in genre_channels_grouped[ch_name][:200]:
                final_combined_output.append(processed_line)

    with open(final_output_file, "w", encoding="utf-8") as iptv_list_file:
        iptv_list_file.writelines(final_combined_output)
    
    logging.info(f"Final IPTV list merged to: {final_output_file}")


# --- Main Execution Flow ---
def main():
    config_dir = os.path.join(os.getcwd(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    urls_file_path = os.path.join(config_dir, 'urls.txt')

    local_channels_directory = os.path.join(os.getcwd(), '地方频道')
    os.makedirs(local_channels_directory, exist_ok=True)
    clear_txt_files(local_channels_directory) # Clear old files

    template_directory = os.path.join(os.getcwd(), '频道模板')
    os.makedirs(template_directory, exist_ok=True)

    # 1. Collect and filter initial channel lists from URLs
    urls_to_process = read_txt_to_array(urls_file_path)
    all_raw_channels = []
    for url in urls_to_process:
        all_raw_channels.extend(process_single_url_source(url))

    filtered_unique_channels = list(set(filter_and_modify_channels(all_raw_channels)))
    logging.info(f"Collected and filtered {len(filtered_unique_channels)} unique channels.")

    # 2. Validate channel URLs (multithreaded)
    # The check_channel_url expects (name, url) tuple directly
    validated_channels_with_times = validate_channels_multithreaded(filtered_unique_channels)
    logging.info(f"Validated {len(validated_channels_with_times)} channels.")

    # 3. Write validated channels to iptv_speed.txt (optional intermediate)
    iptv_speed_file_path = os.path.join(os.getcwd(), 'iptv_speed.txt')
    write_channels_to_file(iptv_speed_file_path, validated_channels_with_times)

    # 4. Categorize and save channels based on templates
    iptv_speed_channels_raw = [item[1] for item in validated_channels_with_times] # Get "name,url" strings
    
    template_files = [f for f in os.listdir(template_directory) if f.endswith('.txt')]

    for template_file in template_files:
        template_channels_names = read_txt_to_array(os.path.join(template_directory, template_file))
        template_name = os.path.splitext(template_file)[0]

        # Filter channels that match names in the current template
        matched_channels_for_template = [
            channel_line for channel_line in iptv_speed_channels_raw
            if channel_line.split(',')[0].strip() in template_channels_names
        ]
        
        # Sort CCTV channels if it's the CCTV template
        if "央视" in template_name or "CCTV" in template_name:
            matched_channels_for_template = sort_cctv_channels(matched_channels_for_template)
            
        # Add genre header and write to output file
        output_file_path = os.path.join(local_channels_directory, f"{template_name}_iptv.txt")
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(f"{template_name},#genre#\n")
            for channel_line in matched_channels_for_template:
                f.write(channel_line + '\n')
        logging.info(f"Categorized channels written to: {output_file_path}")

    # 5. Merge all categorized _iptv.txt files into a final list
    merge_and_finalize_iptv_list(local_channels_directory)

    # 6. Clean up temporary files
    try:
        os.remove('iptv.txt') # This one might not be created anymore with new flow
        os.remove('iptv_speed.txt')
        logging.info("Cleaned up temporary files: iptv.txt, iptv_speed.txt")
    except OSError as e:
        logging.warning(f"Could not remove temporary files: {e}")

if __name__ == "__main__":
    main()
