import base64
import requests
import yaml # 仍然保留yaml库用于解析config.yaml，但不再用于生成输出
import os
import re
from datetime import datetime

bing_counter = 0
vmess_errors = set()

def fetch_data(url):
    """从给定的URL获取数据。"""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"无法从 {url} 获取数据: {e}")
        return None

def decode_base64(data):
    """解码Base64编码的数据，同时处理URL安全编码和填充。"""
    try:
        # 移除任何非Base64字符，然后添加正确的填充
        cleaned_data = re.sub(r'[^A-Za-z0-9+/=]', '', data)
        return base64.b64decode(cleaned_data + '=' * (-len(cleaned_data) % 4)).decode('utf-8')
    except Exception:
        return data

def extract_host_port(server_port):
    """从'host:port'字符串中提取主机和端口。"""
    m = re.match(r'^\[?([0-9a-fA-F:.]+)\]?:([0-9]+)$', server_port)
    if m:
        return m.group(1), int(m.group(2))
    parts = server_port.rsplit(':', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return server_port, None

# 以下解析函数现在返回原始链接本身，而不是字典，或者为非链接的YAML代理返回None
def parse_ss(link):
    """返回Shadowsocks (ss://) 链接本身。"""
    if link.startswith('ss://'):
        return link
    return None

def parse_vmess(link):
    """返回VMess (vmess://) 链接本身。"""
    if link.startswith('vmess://'):
        return link
    return None

def parse_trojan(link):
    """返回Trojan (trojan://) 链接本身。"""
    if link.startswith('trojan://'):
        return link
    return None

def parse_vless(link):
    """返回VLESS (vless://) 链接本身。"""
    if link.startswith('vless://'):
        return link
    return None

def parse_hysteria2(link):
    """返回Hysteria2 (hysteria2://) 链接本身。"""
    if link.startswith('hysteria2://'):
        return link
    return None

# extract_flag 函数将不再用于命名输出文件，因为它与原始链接格式不符
# 但是，我们可以为每个链接添加一个计数器作为注释，如果需要的话
def extract_info_and_add_counter(link_type, link_data):
    """
    此函数现在仅用于内部计数，并可能提取识别信息用于去重。
    返回一个用于去重的值（例如 server, port），以及原始链接。
    """
    global bing_counter
    bing_counter += 1 # 每次处理一个链接，计数器加一

    if link_type == 'ss':
        # 对于ss，我们可能需要解析出server和port来进行去重
        try:
            link_body = link_data[5:]
            if '#' in link_body:
                link_body, _ = link_body.split('#', 1)
            
            if '@' in link_body:
                _, serverinfo = link_body.split('@', 1)
                server, port = extract_host_port(serverinfo)
            else:
                decoded = base64.urlsafe_b64decode(link_body + '=' * (-len(link_body) % 4)).decode('utf-8')
                _, server_port = decoded.rsplit('@', 1)
                server, port = extract_host_port(server_port)
            return (server, port) if port is not None else None, link_data
        except Exception:
            return None, link_data
    elif link_type == 'vmess':
        try:
            b64 = link_data[8:]
            b64 = re.sub(r'[^A-Za-z0-9+/=]', '', b64)
            b64 += '=' * (-len(b64) % 4)
            vmess_json = yaml.safe_load(base64.b64decode(b64).decode('utf-8'))
            return (vmess_json['add'], int(vmess_json['port'])), link_data
        except Exception:
            return None, link_data
    elif link_type in ['trojan', 'vless', 'hysteria2']:
        try:
            # 这些协议的host:port部分在'//'之后，'?'或'/'之前
            link_body = link_data.split('://', 1)[1]
            if '#' in link_body:
                link_body, _ = link_body.split('#', 1)
            
            if '@' in link_body:
                _, serverinfo = link_body.split('@', 1)
            else: # 对于VLESS，可能没有@
                serverinfo = link_body
            
            server, port = extract_host_port(serverinfo.split('?', 1)[0].split('/', 1)[0])
            return (server, port) if port is not None else None, link_data
        except Exception:
            return None, link_data
    return None, link_data # 如果无法解析出server/port，则不进行去重

def generate_plain_text_links(links):
    """将代理链接列表生成为明文格式的字符串。"""
    return "\n".join(links)

def main(urls):
    """主函数，用于获取、解析和保存代理配置。"""
    global bing_counter
    bing_counter = 0 # 每次运行重置计数器
    all_links = []
    seen = set() # 用于存储 (server, port) 对，避免重复

    for url in urls:
        print(f"正在从 {url} 获取数据...")
        raw_data = fetch_data(url)
        if raw_data is None:
            continue

        # 特别处理 config.yaml，由于其内容是YAML结构，无法直接还原为原始链接
        # 因此，此脚本将跳过从config.yaml生成明文链接
        if url.endswith('.yaml'):
            print(f"注意: {url} 是YAML格式，无法直接转换为明文代理链接，将跳过。")
            continue # 跳过YAML文件

        decoded_data = decode_base64(raw_data)
        lines = decoded_data.splitlines()
        for line in lines:
            line = line.strip()
            # 检查行是否以任何已知的协议前缀开头
            if not line or not any(line.startswith(s) for s in ['ss://','vmess://','trojan://','vless://','hysteria2://']):
                continue
            
            link_type = None
            if line.startswith('ss://'):
                link_type = 'ss'
            elif line.startswith('vmess://'):
                link_type = 'vmess'
            elif line.startswith('trojan://'):
                link_type = 'trojan'
            elif line.startswith('vless://'):
                link_type = 'vless'
            elif line.startswith('hysteria2://'):
                link_type = 'hysteria2'
            
            if link_type:
                identifier, original_link = extract_info_and_add_counter(link_type, line)
                if identifier: # 如果成功提取了用于去重的信息
                    if identifier not in seen:
                        seen.add(identifier)
                        all_links.append(original_link)
                else: # 如果无法提取去重信息，直接添加（可能重复）
                    all_links.append(original_link)


    if not all_links:
        print("未找到有效的代理链接！")
        return

    # 保存到 data/clash.txt (现在是txt文件)
    os.makedirs('data', exist_ok=True)
    plain_text_content = generate_plain_text_links(all_links)
    output_path_data = 'data/clash.txt' # 文件名改为.txt
    with open(output_path_data, 'w', encoding='utf-8') as f:
        f.write(plain_text_content)
    print(f"Clash 代理链接已保存到 {output_path_data}")

    # 将结果按1000行分片输出到 sub 目录
    current_time = datetime.now()
    year_dir = current_time.strftime('%Y')
    month_dir = current_time.strftime('%m')
    
    # 固定文件名，仅使用日期作为前缀
    date_prefix = current_time.strftime('%Y-%m-%d') 
    
    sub_base_dir = os.path.join('sub', year_dir, month_dir)
    os.makedirs(sub_base_dir, exist_ok=True)

    links_per_file = 1000
    total_links = len(all_links)
    num_files = (total_links + links_per_file - 1) // links_per_file # 计算需要的文件数量

    for i in range(num_files):
        start_index = i * links_per_file
        end_index = min((i + 1) * links_per_file, total_links)
        part_links = all_links[start_index:end_index]

        part_plain_text_content = generate_plain_text_links(part_links)
        # 文件名保持 YYYY-MM-DD_clash_part_X.txt 格式
        part_file_name = f"{date_prefix}_clash_part_{i+1}.txt" 
        part_output_path = os.path.join(sub_base_dir, part_file_name)
        
        with open(part_output_path, 'w', encoding='utf-8') as f:
            f.write(part_plain_text_content)
        print(f"Clash 分片代理链接已保存到 {part_output_path} (包含 {len(part_links)} 条代理)")


if __name__ == "__main__":
    urls = [
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/ss.txt',
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/config.yaml', # 此URL的内容将无法转换为明文链接并被跳过
        'https://raw.githubusercontent.com/qjlxg/hy2/refs/heads/main/configtg.txt',
    ]
    main(urls)
