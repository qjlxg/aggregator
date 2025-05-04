import os
import re
import csv
import yaml
import json
import base64
import socket
import requests
import geoip2.database

# 配置（使用绝对路径）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
URL_LIST_PATH = os.path.join(BASE_DIR, 'data', '1.list')
RAW_OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'A.txt')
CLASH_OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'c.yml')
CSV_OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'b.csv') 
GEOIP_DB_PATH = os.path.join(BASE_DIR, 'clash', 'Country.mmdb')

SUPPORTED_SCHEMES = ['vmess://', 'ss://', 'trojan://', 'vless://', 'hysteria2://']
COUNTRY_FLAGS = {
    'CN': '🇨🇳', 'HK': '🇭🇰', 'TW': '🇹🇼', 'JP': '🇯🇵',
    'KR': '🇰🇷', 'SG': '🇸🇬', 'US': '🇺🇸', 'GB': '🇬🇧',
    'RU': '🇷🇺', 'IN': '🇮🇳', 'DE': '🇩🇪', 'CA': '🇨🇦',
    'AU': '🇦🇺', 'FR': '🇫🇷', 'IT': '🇮🇹', 'NL': '🇳🇱',
}

def fetch_urls(url_list_path, output_path):
    """从URL列表下载内容并保存到文件"""
    print(f"读取输入文件: {url_list_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        with open(url_list_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        print(f"找到 {len(urls)} 个 URL")
    except FileNotFoundError:
        print(f"错误：输入文件 {url_list_path} 不存在")
        return {}
    url_count = {}
    with open(output_path, 'w', encoding='utf-8') as out:
        for url in urls:
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                content = resp.text
                out.write(f"# URL: {url}\n{content}\n")
                count = sum(1 for l in content.splitlines() if any(l.startswith(s) for s in SUPPORTED_SCHEMES))
                url_count[url] = count
            except Exception as e:
                print(f"请求 {url} 失败: {e}")
                url_count[url] = 0
    return url_count

def extract_nodes(text):
    """从文本中提取代理节点"""
    nodes = set()
    # 1. Clash YAML格式
    try:
        clash_data = yaml.safe_load(text)
        if isinstance(clash_data, dict) and 'proxies' in clash_data:
            for proxy in clash_data['proxies']:
                nodes.add(yaml.dump(proxy, allow_unicode=True, sort_keys=False))
    except Exception:
        pass
    # 2. Base64编码
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            decoded = base64.b64decode(line + '=' * (-len(line) % 4)).decode('utf-8', errors='ignore')
            for scheme in SUPPORTED_SCHEMES:
                if scheme in decoded:
                    for l in decoded.splitlines():
                        if any(l.startswith(s) for s in SUPPORTED_SCHEMES):
                            nodes.add(l.strip())
        except Exception:
            pass
        # 3. 明文节点
        if any(line.startswith(s) for s in SUPPORTED_SCHEMES):
            nodes.add(line)
    return list(nodes)

def get_country_flag(server, geoip_db_path):
    """根据服务器IP或域名获取国家标志"""
    try:
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', server):
            server = socket.gethostbyname(server)
        with geoip2.database.Reader(geoip_db_path) as reader:
            response = reader.country(server)
            country_code = response.country.iso_code
            return COUNTRY_FLAGS.get(country_code, '🏁')
    except Exception as e:
        print(f"获取国家标志失败: {e}")
        return '🏁'

def parse_url_node(url, geoip_db_path, idx):
    """解析单个节点URL为Clash格式"""
    # vmess
    if url.startswith('vmess://'):
        try:
            vmess_raw = url[8:]
            vmess_raw += '=' * (-len(vmess_raw) % 4)
            data = json.loads(base64.b64decode(vmess_raw).decode('utf-8', errors='ignore'))
            server = data['add']
            flag = get_country_flag(server, geoip_db_path)
            return {
                'name': f"{flag} bing{idx+1}",
                'server': server,
                'port': int(data['port']),
                'type': 'vmess',
                'uuid': data['id'],
                'alterId': int(data.get('aid', 0)),
                'cipher': data.get('scy', 'auto'),
                'network': data.get('net', 'tcp'),
                'tls': bool(data.get('tls', False))
            }
        except Exception as e:
            print(f"解析 vmess 节点失败: {e}")
            return None
    # ss
    if url.startswith('ss://'):
        try:
            parsed = re.split(r'#', url, 1)
            url_main = parsed[0]
            name = parsed[1] if len(parsed) > 1 else 'ss'
            url_main = url_main[5:]
            if '@' in url_main:
                method_pass, server_port = url_main.split('@')
                method, passwd = base64.b64decode(method_pass + '=' * (-len(method_pass) % 4)).decode('utf-8', errors='ignore').split(':', 1)
                server, port = server_port.split(':')
            else:
                decoded = base64.b64decode(url_main + '=' * (-len(url_main) % 4)).decode('utf-8', errors='ignore')
                method, rest = decoded.split(':', 1)
                passwd, server_port = rest.rsplit('@', 1)
                server, port = server_port.split(':')
            flag = get_country_flag(server, geoip_db_path)
            return {
                'name': f"{flag} bing{idx+1}",
                'server': server,
                'port': int(port),
                'type': 'ss',
                'password': passwd,
                'udp': True,
                'cipher': method
            }
        except Exception as e:
            print(f"解析 ss 节点失败: {e}")
            return None
    # trojan
    if url.startswith('trojan://'):
        try:
            p = re.split(r'#', url, 1)
            url_main = p[0][9:]
            name = p[1] if len(p) > 1 else 'trojan'
            pwd, server_port = url_main.split('@')
            server, port = server_port.split(':')
            flag = get_country_flag(server, geoip_db_path)
            return {
                'name': f"{flag} bing{idx+1}",
                'server': server,
                'port': int(port),
                'type': 'trojan',
                'password': pwd,
                'sni': server
            }
        except Exception as e:
            print(f"解析 trojan 节点失败: {e}")
            return None
    # vless
    if url.startswith('vless://'):
        try:
            p = re.split(r'#', url, 1)
            url_main = p[0][8:]
            name = p[1] if len(p) > 1 else 'vless'
            uuid, server_port = url_main.split('@')
            server, port = server_port.split(':')
            flag = get_country_flag(server, geoip_db_path)
            return {
                'name': f"{flag} bing{idx+1}",
                'server': server,
                'port': int(port),
                'type': 'vless',
                'uuid': uuid,
                'tls': True,
                'servername': server
            }
        except Exception as e:
            print(f"解析 vless 节点失败: {e}")
            return None
    # hysteria2
    if url.startswith('hysteria2://'):
        try:
            p = re.split(r'#', url, 1)
            url_main = p[0][11:]
            name = p[1] if len(p) > 1 else 'hysteria2'
            pwd, server_port = url_main.split('@')
            server, port = server_port.split(':')
            flag = get_country_flag(server, geoip_db_path)
            return {
                'name': f"{flag} bing{idx+1}",
                'server': server,
                'port': int(port),
                'type': 'hysteria2',
                'password': pwd
            }
        except Exception as e:
            print(f"解析 hysteria2 节点失败: {e}")
            return None
    return None

def main():
    """主函数：下载URL、解析节点并生成输出文件"""
    print("当前工作目录:", os.getcwd())
    url_count = fetch_urls(URL_LIST_PATH, RAW_OUTPUT_PATH)
    print(f"URL 统计: {url_count}")
    try:
        with open(RAW_OUTPUT_PATH, 'r', encoding='utf-8') as f:
            all_text = f.read()
        raw_nodes = extract_nodes(all_text)
        print(f"提取到 {len(raw_nodes)} 个原始节点")
    except FileNotFoundError:
        print(f"错误：文件 {RAW_OUTPUT_PATH} 不存在")
        return
    clash_nodes = []
    seen = set()
    for idx, node_url in enumerate(raw_nodes):
        node = parse_url_node(node_url, GEOIP_DB_PATH, idx)
        if node:
            key = f"{node['server']}:{node['port']}:{node['type']}"
            if key not in seen:
                seen.add(key)
                clash_nodes.append(node)
    print(f"解析到 {len(clash_nodes)} 个 Clash 节点")
    with open(CLASH_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        yaml.dump({'proxies': clash_nodes}, f, allow_unicode=True, sort_keys=False)
    with open(CSV_OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['URL', '节点数量'])
        for url, count in url_count.items():
            writer.writerow([url, count])
    print(f"已保存 {len(clash_nodes)} 个节点到 {CLASH_OUTPUT_PATH}")

if __name__ == "__main__":
    main()
