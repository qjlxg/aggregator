import requests
import base64
import os
import json
import re
import yaml
from urllib.parse import urlparse, parse_qs, unquote
import hashlib
import socket
import time
import concurrent.futures
import logging
import ipaddress # 新增导入，用于IP地址和CIDR检查

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# --- China Filtering Data (Can be expanded) ---
# Keywords often found in proxy names or server names/domains that indicate China
CHINA_KEYWORDS = [
    "中国", "china", "cn", "🇨🇳", # Common keywords
    "ch", "mainland", "domestic", # Other potential indicators
    ".cn", ".com.cn", ".net.cn", ".org.cn", # Chinese TLDs
    "aliyun", "tencentcloud", "huaweicloud", # Common Chinese cloud providers (can be more specific)
    "baidu", "qq", "wechat", "jd", "taobao", # Common Chinese services (often hosted in China)
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", # Major Chinese cities
]

# Common Chinese IP CIDR blocks (incomplete, for demonstration)
# For a comprehensive list, consider fetching from a reliable source like:
# https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/cn.txt
# Or pre-downloading and using a MaxMind GeoLite2-Country database.
# Using a small, representative set for now to avoid large data files.
CHINA_IP_CIDRS = [
    "1.0.1.0/24", "1.1.1.0/24", "1.1.2.0/23", "1.2.0.0/22", # Part of China Telecom
    "42.48.0.0/12", "42.56.0.0/14", # China Unicom
    "43.224.0.0/13", # China Mobile
    "49.64.0.0/11", "58.0.0.0/8", "60.0.0.0/7", # Various Chinese ranges
    "101.0.0.0/8", "103.0.0.0/8", # Various Chinese ranges
    "111.0.0.0/7", "112.0.0.0/7", "113.0.0.0/8", # Various Chinese ranges
    "114.0.0.0/7", "115.0.0.0/8", "116.0.0.0/7", # Various Chinese ranges
    "117.0.0.0/8", "118.0.0.0/7", "119.0.0.0/8", # Various Chinese ranges
    "120.0.0.0/7", "121.0.0.0/8", "122.0.0.0/7", # Various Chinese ranges
    "123.0.0.0/8", "140.0.0.0/7", "180.0.0.0/8", "182.0.0.0/7", # Various Chinese ranges
    "202.0.0.0/8", "210.0.0.0/7", "211.0.0.0/8", # Various Chinese ranges
    "218.0.0.0/7", "219.0.0.0/8", "220.0.0.0/7", "221.0.0.0/8", "222.0.0.0/8",
    # IPv6 ranges would also be needed for comprehensive filtering
    # "2001:0db8::/32", # Example IPv6
]

# Pre-parse CIDRs for faster lookup
PARSED_CHINA_CIDRS = []
for cidr in CHINA_IP_CIDRS:
    try:
        PARSED_CHINA_CIDRS.append(ipaddress.ip_network(cidr, strict=False))
    except ValueError as e:
        logger.error(f"Invalid CIDR in CHINA_IP_CIDRS: {cidr} - {e}")

def is_ip_in_china(ip_address):
    """Checks if an IP address falls within the defined Chinese CIDR ranges."""
    try:
        ip = ipaddress.ip_address(ip_address)
        for network in PARSED_CHINA_CIDRS:
            if ip in network:
                return True
        return False
    except ValueError: # Not a valid IP address
        return False

def is_likely_china_node(proxy_data):
    """
    Checks if a proxy node is likely located in China based on keywords or IP.
    Returns True if it's likely in China, False otherwise.
    """
    name_lower = proxy_data.get('name', '').lower()
    server_lower = proxy_data.get('server', '').lower()

    # 1. Keyword check
    for keyword in CHINA_KEYWORDS:
        if keyword in name_lower or keyword in server_lower:
            logger.debug(f"  Node '{proxy_data.get('name')}' excluded by keyword: '{keyword}'")
            return True
    
    # 2. IP CIDR check
    server_ip = None
    try:
        # Attempt to resolve hostname to IP
        # Using socket.gethostbyname for simplicity, but it's blocking.
        # For a large number of nodes, consider a non-blocking DNS resolver if this becomes a bottleneck.
        server_ip = socket.gethostbyname(proxy_data.get('server'))
        if is_ip_in_china(server_ip):
            logger.debug(f"  Node '{proxy_data.get('name')}' excluded by China IP range: {server_ip}")
            return True
    except socket.gaierror:
        logger.warning(f"  Could not resolve IP for server: {proxy_data.get('server')}. Skipping IP check for this node.")
    except Exception as e:
        logger.error(f"  Error during IP resolution for {proxy_data.get('server')}: {e}")

    return False


# --- Proxy Parsing Functions ---
def generate_proxy_fingerprint(proxy_data):
    """
    根据代理的关键连接信息生成一个唯一的哈希指纹。
    这用于识别和去重相同的代理，即使它们的名称不同。
    """
    parts = []
    # 尽可能包含所有核心连接参数，并确保它们是字符串类型
    parts.append(str(proxy_data.get('type', '')))
    parts.append(str(proxy_data.get('server', '')))
    parts.append(str(proxy_data.get('port', '')))
    parts.append(str(proxy_data.get('uuid', '')))
    parts.append(str(proxy_data.get('password', '')))
    parts.append(str(proxy_data.get('cipher', '')))<br>    parts.append(str(proxy_data.get('network', '')))<br>    parts.append(str(proxy_data.get('tls', '')))<br>    parts.append(str(proxy_data.get('servername', '')))<br>    parts.append(str(proxy_data.get('ws-path', '')))<br>    parts.append(str(proxy_data.get('plugin-info', '')))<br>    parts.append(str(proxy_data.get('alpn', '')))<br>    parts.append(str(proxy_data.get('flow', ''))) # VLESS flow<br>    parts.append(str(proxy_data.get('fingerprint', ''))) # TLS fingerprint

    unique_string = "_".join(parts)
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()

def parse_vmess(vmess_url):
    try:
        json_str = base64.b64decode(vmess_url[8:]).decode('utf-8')
        config = json.loads(json_str)

        name = config.get('ps', f"Vmess-{config.get('add')}")
        server = config.get('add')
        port = config.get('port')
        uuid = config.get('id')
        alterId = config.get('aid', 0)
        cipher = config.get('scy', 'auto')
        network = config.get('net', 'tcp')
        tls = config.get('tls', '') == 'tls'
        servername = config.get('sni', config.get('host', '')) if tls else ''
        skip_cert_verify = config.get('v', '') == '1'

        proxy = {
            'name': name,
            'type': 'vmess',
            'server': server,
            'port': port,
            'uuid': uuid,
            'alterId': alterId,
            'cipher': cipher,
            'network': network,
            'tls': tls,
        }

        if servername:
            proxy['servername'] = servername
        if skip_cert_verify:
            proxy['skip-cert-verify'] = True

        if network == 'ws':
            proxy['ws-path'] = config.get('path', '/')
            if config.get('headers'):
                try:
                    ws_headers_dict = json.loads(config['headers'])
                    proxy['ws-headers'] = ws_headers_dict
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Vmess {name}: Invalid ws-headers format, skipping: {config.get('headers')}")
        
        # 增加对 Vmess 的 alpn 支持
        if config.get('alpn'):
            proxy['alpn'] = config['alpn']

        return proxy
    except Exception as e:
        logger.warning(f"解析 Vmess 链接失败: {vmess_url[:50]}...，原因: {e}")
        return None

def parse_trojan(trojan_url):
    try:
        parsed = urlparse(trojan_url)
        password = parsed.username
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"Trojan-{server}"

        params = parse_qs(parsed.query)
        tls = True # Trojan 协议强制 TLS
        skip_cert_verify = params.get('allowInsecure', ['0'])[0] == '1'
        servername = params.get('sni', [server])[0]

        proxy = {
            'name': name,
            'type': 'trojan',
            'server': server,
            'port': port,
            'password': password,
            'tls': tls,
        }
        if servername:
            proxy['servername'] = servername
        if skip_cert_verify:
            proxy['skip-cert-verify'] = True
        
        # 支持 VLESS 兼容的 flow 参数 (Trojan-Go 可能会有)
        if params.get('flow'):
            proxy['flow'] = params['flow'][0]

        # 支持 alpn
        if params.get('alpn'):
            proxy['alpn'] = ','.join(params['alpn'])

        return proxy
    except Exception as e:
        logger.warning(f"解析 Trojan 链接失败: {trojan_url[:50]}...，原因: {e}")
        return None

# 修改 ShadowSocks 解析器，使用更严格的正则匹配
def parse_shadowsocks(ss_url):
    try:
        encoded_part = ss_url[5:]

        name = "Shadowsocks"
        plugin_info_str = ""

        if '#' in encoded_part:
            encoded_part, fragment = encoded_part.split('#', 1)
            name = unquote(fragment)

        if '/?plugin=' in encoded_part:
            encoded_part, plugin_info_str = encoded_part.split('/?plugin=', 1)
            plugin_info_str = unquote(plugin_info_str)

        # Base64 解码，处理可能的填充
        missing_padding = len(encoded_part) % 4
        if missing_padding:
            encoded_part += '=' * (4 - missing_padding)
        
        try:
            decoded_bytes = base64.urlsafe_b64decode(encoded_part)
            decoded_str = decoded_bytes.decode('utf-8', errors='ignore') # 忽略解码错误，确保不崩溃
            
            # 使用正则表达式匹配 method:password@server:port 结构
            # 兼容多种格式，如 aes-128-gcm:password@server:port 或 method@server:port
            # 优先匹配 method:password@server:port
            match = re.match(r'^([^:]+):([^@]+)@([^:]+):(\d+)$', decoded_str)
            if not match:
                # 尝试匹配 method@server:port
                match = re.match(r'^([^@]+)@([^:]+):(\d+)$', decoded_str)
                if match: # 如果是 method@server:port 格式，则 password 为空
                    method = match.group(1)
                    password = ""
                    server = match.group(2)
                    port = int(match.group(3))
                else:
                    raise ValueError("Invalid format: Not method:password@server:port or method@server:port")
            else:
                method = match.group(1)
                password = match.group(2)
                server = match.group(3)
                port = int(match.group(4))

            proxy = {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': port,
                'cipher': method,
                'password': password,
            }

            if plugin_info_str:
                # 解析 plugin-info 为 Clash 期望的格式 (字典)
                # 示例: obfs-local;obfs=tls;obfs-host=example.com
                plugin_parts = plugin_info_str.split(';')
                plugin_type = plugin_parts[0]
                plugin_opts = {}
                for part in plugin_parts[1:]:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        plugin_opts[key] = value

                proxy['plugin'] = plugin_type
                proxy['plugin-opts'] = plugin_opts

            return proxy
        except (base64.binascii.Error, ValueError) as decode_err:
            raise ValueError(f"Base64 decoding or regex matching error: {decode_err}")
    except Exception as e:
        logger.warning(f"解析 Shadowsocks 链接失败: {ss_url[:100]}...，原因: {e}")
        return None

def parse_hysteria2(hy2_url):
    try:
        parsed = urlparse(hy2_url)
        uuid = parsed.username
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"Hysteria2-{server}"

        params = parse_qs(parsed.query)
        tls = params.get('security', [''])[0].lower() == 'tls'
        servername = params.get('sni', [''])[0]
        skip_cert_verify = params.get('insecure', ['0'])[0] == '1'
        fast_open = params.get('fastopen', ['0'])[0] == '1'
        alpn = params.get('alpn', [''])
        if alpn and alpn[0]:
            alpn = alpn[0].split(',')

        proxy = {
            'name': name,
            'type': 'hysteria2',
            'server': server,
            'port': port,
            'password': uuid, # Hysteria2 的密码就是 uuid
            'tls': tls,
            'skip-cert-verify': skip_cert_verify,
            'fast-open': fast_open,
        }
        if servername:
            proxy['servername'] = servername
        if alpn and alpn[0]:
            proxy['alpn'] = alpn

        return proxy
    except Exception as e:
        logger.warning(f"解析 Hysteria2 链接失败: {hy2_url[:50]}...，原因: {e}")
        return None

# --- Connectivity Test Function ---
def test_tcp_connectivity(server, port, timeout=1, retries=1, delay=0.5):
    """
    尝试与指定的服务器和端口建立TCP连接，测试连通性。
    增加重试机制，以应对瞬时网络抖动或服务器短暂问题。
    返回 True 如果连接成功，否则返回 False。
    **参数已调整为更快的失败策略。**
    """
    # 获取环境变量中的参数
    timeout_env = os.environ.get("TCP_TIMEOUT")
    retries_env = os.environ.get("TCP_RETRIES")
    delay_env = os.environ.get("TCP_DELAY")

    timeout = float(timeout_env) if timeout_env else timeout
    retries = int(retries_env) if retries_env else retries
    delay = float(delay_env) if delay_env else delay

    start_time = time.time()
    for i in range(retries + 1):
        try:
            sock = socket.create_connection((server, port), timeout=timeout)
            sock.close()
            # 返回 (True, 延迟)
            return True, time.time() - start_time
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            # logger.debug(f"连接尝试 {i+1}/{retries+1} 失败 for {server}:{port} - {e}") # 调试级别输出
            if i < retries:
                time.sleep(delay)
        except Exception as e:
            logger.error(f"TCP连接测试发生未知错误: {server}:{port} - {e}")
            return False, float('inf') # 返回无限大延迟表示失败
    return False, float('inf') # 所有重试都失败，返回无限大延迟

# --- Fetch and Decode URLs (Modified for deduplication and naming) ---
def fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test=True, enable_china_filter=False):
    all_raw_proxies = [] # 收集所有解析出的代理（包含重复的）
    successful_urls_this_run = set() # 本次运行成功获取的URL
    
    # 获取要排除的节点服务器列表 (黑名单)
    exclude_servers_str = os.environ.get("EXCLUDE_NODES_BY_SERVER", "")
    exclude_servers = [s.strip().lower() for s in exclude_servers_str.split(',') if s.strip()]

    EXCLUDE_KEYWORDS = [
        "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
        "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net",
        "t.me", "api.w.org",
        "html", "css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp", "xml", "json", "txt",
        "google-analytics.com", "cloudflare.com/cdn-cgi/", "gstatic.com", "googleapis.com",
        "disqus.com", "gravatar.com", "s.w.org",
        "amazon.com", "aliyuncs.com", "tencentcos.cn",
        "cdn.bootcss.com", "cdnjs.cloudflare.com",
        "bit.ly", "tinyurl.com", "cutt.ly", "shorturl.at", "surl.li", "suo.yt", "v1.mk",
        "youtube.com", "facebook.com", "twitter.com", "weibo.com",
        "mail.google.com", "docs.google.com",
        "microsoft.com", "apple.com", "baidu.com", "qq.com",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".zip", ".rar", ".7z", ".tar.gz", ".exe", ".dmg", ".apk",
        "/assets/", "/static/", "/images/", "/scripts/", "/styles/", "/fonts/",
        "robots.txt", "sitemap.xml", "favicon.ico",
        "rss", "atom",
        "/LICENSE", "/README.md", "/CHANGELOG.md",
        ".git", ".svn",
        "swagger-ui.html", "openapi.json"
    ]

    for url_idx, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue

        if any(keyword in url for keyword in EXCLUDE_KEYWORDS):
            logger.info(f"Skipping non-subscription link (filtered by keyword): {url}")
            continue

        logger.info(f"[{url_idx+1}/{len(urls)}] Processing URL: {url}")
        current_proxies_from_url = []
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            content = response.content

            def try_parse_yaml(text):
                try:
                    data = yaml.safe_load(text)
                    if isinstance(data, dict) and 'proxies' in data and isinstance(data['proxies'], list):
                        return data['proxies']
                    elif isinstance(data, list) and all(isinstance(item, dict) and 'type' in item for item in data):
                        return data
                    return None
                except yaml.YAMLError:
                    return None

            def try_parse_json_nodes(text):
                try:
                    data = json.loads(text)
                    if isinstance(data, list) and all(isinstance(item, dict) and 'v' in item for item in data):
                        parsed_list = []
                        for node in data:
                            vmess_link = f"vmess://{base64.b64encode(json.dumps(node).encode('utf-8')).decode('utf-8')}"
                            p = parse_vmess(vmess_link)
                            if p: parsed_list.append(p)
                        return parsed_list
                    return None
                except json.JSONDecodeError:
                    return None

            try:
                decoded_content = content.decode('utf-8')

                yaml_proxies = try_parse_yaml(decoded_content)
                if yaml_proxies:
                    current_proxies_from_url.extend(yaml_proxies)
                    logger.info(f"  --- URL: {url} Identified as YAML subscription with {len(yaml_proxies)} proxies ---")
                else:
                    json_proxies = try_parse_json_nodes(decoded_content)
                    if json_proxies:
                        current_proxies_from_url.extend(json_proxies)
                        logger.info(f"  --- URL: {url} Identified as JSON node list with {len(json_proxies)} proxies ---")
                    else:
                        if len(decoded_content.strip()) > 0 and len(decoded_content.strip()) % 4 == 0 and re.fullmatch(r'[A-Za-z0-9+/=]*', decoded_content.strip()):
                            try:
                                temp_decoded = base64.b64decode(decoded_content.strip()).decode('utf-8')
                                lines = temp_decoded.split('\n')
                                parsed_line_count = 0
                                for line in lines:
                                    line = line.strip()
                                    p = None
                                    if line.startswith("vmess://"):
                                        p = parse_vmess(line)
                                    elif line.startswith("trojan://"):
                                        p = parse_trojan(line)
                                    elif line.startswith("ss://"):
                                        p = parse_shadowsocks(line)
                                    elif line.startswith("hysteria2://"):
                                        p = parse_hysteria2(line)
                                    
                                    if p: current_proxies_from_url.append(p); parsed_line_count += 1
                                if parsed_line_count > 0:
                                    logger.info(f"  --- URL: {url} Base64 decoded and identified {parsed_line_count} proxy nodes ---")
                                else:
                                    logger.warning(f"  --- URL: {url} Base64 decoded successfully, but content doesn't match known proxy format.---")
                            except (base64.binascii.Error, UnicodeDecodeError):
                                logger.warning(f"  --- URL: {url} Looks like Base64 but failed to decode, treating as plaintext.---")

                        if not current_proxies_from_url:
                            lines = decoded_content.split('\n')
                            parsed_line_count = 0
                            for line in lines:
                                line = line.strip()
                                p = None
                                if line.startswith("vmess://"):
                                    p = parse_vmess(line)
                                elif line.startswith("trojan://"):
                                    p = parse_trojan(line)
                                elif line.startswith("ss://"):
                                    p = parse_shadowsocks(line)
                                elif line.startswith("hysteria2://"):
                                    p = parse_hysteria2(line)
                                if p: current_proxies_from_url.append(p); parsed_line_count += 1
                            if parsed_line_count > 0:
                                logger.info(f"  --- URL: {url} Identified as plaintext {parsed_line_count} proxy nodes ---")
                            else:
                                logger.warning(f"  --- URL: {url} Content not identified as valid subscription format (UTF-8).---")

            except UnicodeDecodeError:
                logger.warning(f"  --- URL: {url} UTF-8 decoding failed, trying Base64 decoding.---")
                try:
                    cleaned_content = content.strip()
                    temp_decoded = base64.b64decode(cleaned_content).decode('utf-8')

                    yaml_proxies = try_parse_yaml(temp_decoded)
                    if yaml_proxies:
                        current_proxies_from_url.extend(yaml_proxies)
                        logger.info(f"  --- URL: {url} Base64 decoded to YAML subscription with {len(yaml_proxies)} proxies ---")
                    else:
                        json_proxies = try_parse_json_nodes(temp_decoded)
                        if json_proxies:
                            current_proxies_from_url.extend(json_proxies)
                            logger.info(f"  --- URL: {url} Base64 decoded to JSON node list with {len(json_proxies)} proxies ---")
                        else:
                            lines = temp_decoded.split('\n')
                            parsed_line_count = 0
                            for line in lines:
                                line = line.strip()
                                p = None
                                if line.startswith("vmess://"):
                                    p = parse_vmess(line)
                                elif line.startswith("trojan://"):
                                    p = parse_trojan(line)
                                elif line.startswith("ss://"):
                                    p = parse_shadowsocks(line)
                                elif line.startswith("hysteria2://"):
                                    p = parse_hysteria2(line)
                                if p: current_proxies_from_url.append(p); parsed_line_count += 1
                            if parsed_line_count > 0:
                                logger.info(f"  --- URL: {url} Base64 decoded to {parsed_line_count} proxy nodes ---")
                            else:
                                logger.warning(f"  --- URL: {url} Base64 decoded successfully, but content doesn't match known proxy format.---")

                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    logger.error(f"  --- URL: {url} Base64 decoding or UTF-8 conversion failed: {decode_err} ---")
                    content.decode('latin-1', errors='ignore') 
                    logger.warning(f"Warning: Could not decode content from {url} to UTF-8 or Base64. Using latin-1 and ignoring errors.")

            if current_proxies_from_url:
                all_raw_proxies.extend(current_proxies_from_url)
                successful_urls_this_run.add(url) # 标记此URL本次成功下载和解析

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from URL: {url}, reason: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing URL {url}: {e}")

    # --- 去重和连通性测试 (并行化) ---
    unique_proxies_for_test = {}
    for proxy_dict in all_raw_proxies:
        if proxy_dict:
            # 检查黑名单
            server_to_check = str(proxy_dict.get('server', '')).lower()
            if any(s in server_to_check for s in exclude_servers):
                logger.info(f"Skipping proxy {proxy_dict.get('name', 'unknown')} (server: {server_to_check}) due to blacklisted server.")
                continue

            # 检查是否是中国节点
            if enable_china_filter and is_likely_china_node(proxy_dict):
                logger.info(f"Skipping proxy {proxy_dict.get('name', 'unknown')} (server: {proxy_dict.get('server')}) due to likely China location.")
                continue

            fingerprint = generate_proxy_fingerprint(proxy_dict)
            if fingerprint not in unique_proxies_for_test:
                unique_proxies_for_test[fingerprint] = proxy_dict
    
    proxies_to_test_list = list(unique_proxies_for_test.values())
    final_filtered_proxies = []
    
    total_testable_proxies = len(proxies_to_test_list)
    successful_proxy_count = 0

    if enable_connectivity_test and total_testable_proxies > 0:
        logger.info(f"\n开始并行连通性测试，共 {total_testable_proxies} 个唯一代理...")
        max_workers = int(os.environ.get("MAX_WORKERS", 30)) # 可配置并行工作线程数
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(test_tcp_connectivity, p['server'], p['port']): p
                for p in proxies_to_test_list if p.get('server') and isinstance(p.get('port'), int)
            }

            processed_count = 0
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy_dict = future_to_proxy[future]
                server = proxy_dict.get('server')
                port = proxy_dict.get('port')
                processed_count += 1

                try:
                    is_reachable, latency = future.result()
                    if is_reachable:
                        base_name = f"{proxy_dict.get('type', 'unknown').upper()}-{proxy_dict.get('server', 'unknown')}"
                        proxy_dict['name'] = f"{base_name}-{generate_proxy_fingerprint(proxy_dict)[:8]} (Ping: {int(latency*1000)}ms)"
                        final_filtered_proxies.append(proxy_dict)
                        successful_proxy_count += 1
                    else:
                        pass
                except Exception as exc:
                    logger.error(f"    连通性测试 {server}:{port} 时发生异常: {exc}")
                
                if processed_count % 50 == 0 or processed_count == total_testable_proxies:
                    logger.info(f"    进度: 已测试 {processed_count}/{total_testable_proxies} 个代理...")

    else:
        logger.info("跳过连通性测试 (已禁用)。所有解析出的唯一代理都会被添加。")
        for proxy_dict in proxies_to_test_list:
            base_name = f"{proxy_dict.get('type', 'unknown').upper()}-{proxy_dict.get('server', 'unknown')}"
            proxy_dict['name'] = f"{base_name}-{generate_proxy_fingerprint(proxy_dict)[:8]}"
            final_filtered_proxies.append(proxy_dict)
            successful_proxy_count += 1

    logger.info(f"成功解析、去重、测试并聚合了 {len(final_filtered_proxies)} 个唯一且可达的代理节点。")
    return final_filtered_proxies, list(successful_urls_this_run), successful_proxy_count

# --- GitHub API Helpers ---
def get_github_file_content(api_url, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.com.v3.raw"}
    try:
        logger.info(f"尝试从 GitHub API 获取文件: {api_url}")
        response = requests.get(api_url, headers=headers, timeout=10)
        logger.info(f"GitHub API 响应状态码: {response.status_code}")
        
        sha = response.headers.get("X-GitHub-Sha")
        if sha is None:
            etag = response.headers.get("ETag")
            if etag:
                sha = etag.strip('"')
                logger.debug(f"X-GitHub-Sha 为 None，从 ETag 获取到 SHA: {sha}")
            else:
                logger.warning("既未获取到 X-GitHub-Sha，也未获取到 ETag。")
        else:
            logger.debug(f"从 X-GitHub-Sha 获取到 SHA: {sha}")
        
        response.raise_for_status()
        return response.text, sha
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error fetching file from GitHub (HTTP Error): {http_err}. Response: {response.text[:200] if response else 'N/A'}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error fetching file from GitHub (Request Error): {req_err}")
        return None, None
    except Exception as e:
        logger.error(f"Error fetching file from GitHub (Other Error): {e}")
        return None, None

def update_github_file_content(repo_contents_api_base, token, file_path, new_content, sha, commit_message):
    url = f"{repo_contents_api_base}/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.com.v3+json",
        "Content-Type": "application/json"
    }
    data = {
        "message": commit_message,
        "content": base64.b64encode(new_content.encode('utf-8')).decode('utf-8'),
        "sha": sha
    }
    try:
        response = requests.put(url, headers=headers, data=json.dumps(data), timeout=10)
        response.raise_for_status()
        logger.info(f"Successfully updated {file_path} on GitHub.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error updating file on GitHub: {e}. Response: {response.text[:200] if response else 'N/A'}")
        if response and response.status_code == 409:
            logger.warning("Conflict: File content changed on GitHub before commit. Please re-run.")
        return False

# --- Main Function ---
def main():
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    template_file_path = os.environ.get("CLASH_TEMPLATE_PATH", "clash_template.yml")

    try:
        parts = url_list_repo_api.split('/')
        if len(parts) < 8 or parts[2] != 'api.github.com' or parts[3] != 'repos' or parts[6] != 'contents':
            raise ValueError("URL_LIST_REPO_API does not seem to be a valid GitHub Content API URL.")
            
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except ValueError as ve:
        logger.error(f"Error: {ve}")
        logger.error("Please ensure URL_LIST_REPO_API is correctly set to a GitHub Content API URL (e.g., https://api.github.com/repos/user/repo/contents/path/to/file.txt).")
        exit(1)
    except IndexError:
        logger.error("Error: URL_LIST_REPO_API format is incorrect or incomplete. Cannot extract owner, repo, or file path.")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        logger.error("Error: Environment variables BOT or URL_LIST_REPO_API are not set!")
        logger.error("Please ensure you've correctly set these variables in GitHub Actions secrets/variables.")
        exit(1)

    # 获取 URL 列表和它的 SHA
    logger.info("Fetching URL list and its SHA from GitHub...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        logger.error("Could not get URL list or its SHA, script terminated.")
        exit(1)

    original_urls = set(url_content.strip().split('\n'))
    logger.info(f"Fetched {len(original_urls)} subscription URLs from GitHub.")

    enable_connectivity_test = os.environ.get("ENABLE_CONNECTIVITY_TEST", "true").lower() == "true"
    enable_china_filter = os.environ.get("EXCLUDE_CHINA_NODES", "false").lower() == "true"

    # 执行代理抓取、解析、去重和测试
    all_parsed_proxies, successful_urls_this_run, successful_proxy_count = \
        fetch_and_decode_urls_to_clash_proxies(list(original_urls), enable_connectivity_test, enable_china_filter)

    # --- 处理 URL 列表的更新 ---
    failed_urls_file = "failed_urls.json"
    failed_urls_tracking = {}
    if os.path.exists(failed_urls_file):
        try:
            with open(failed_urls_file, "r") as f:
                failed_urls_tracking = json.load(f)
            logger.info(f"Loaded failed URLs tracking from {failed_urls_file}.")
        except json.JSONDecodeError:
            logger.warning(f"Could not decode {failed_urls_file}, starting with empty tracking.")

    new_urls_for_repo = set()
    failed_url_threshold = int(os.environ.get("FAILED_URL_THRESHOLD", 3))

    for url in original_urls:
        if url in successful_urls_this_run:
            new_urls_for_repo.add(url)
            if url in failed_urls_tracking:
                del failed_urls_tracking[url]
        else:
            failed_urls_tracking[url] = failed_urls_tracking.get(url, 0) + 1
            if failed_urls_tracking[url] < failed_url_threshold:
                new_urls_for_repo.add(url)
                logger.warning(f"URL '{url}' failed to fetch/parse (count: {failed_urls_tracking[url]}). Retaining for now.")
            else:
                logger.error(f"URL '{url}' failed {failed_urls_tracking[url]} times, removing from list.")
    
    with open(failed_urls_file, "w") as f:
        json.dump(failed_urls_tracking, f)
    logger.info(f"Updated failed URLs tracking saved to {failed_urls_file}.")

    new_url_list_content = "\n".join(sorted(list(new_urls_for_repo)))

    if new_url_list_content.strip() != url_content.strip():
        logger.info("Updating GitHub url.txt file...")
        commit_message = "feat: Update url.txt with valid subscription links (auto-filtered)"
        update_success = update_github_file_content(
            repo_contents_api_base,
            bot_token,
            file_path_in_repo,
            new_url_list_content,
            url_file_sha,
            commit_message
        )
        if update_success:
            logger.info("url.txt file updated successfully.")
        else:
            logger.error("Failed to update url.txt file.")
    else:
        logger.info("url.txt file content unchanged, no update needed.")

    # --- 构建 Clash 完整配置 ---
    clash_config = {}
    try:
        with open(template_file_path, 'r', encoding='utf-8') as f:
            clash_config = yaml.safe_load(f)
        logger.info(f"Loaded Clash configuration template from {template_file_path}.")
    except FileNotFoundError:
        logger.critical(f"Clash template file '{template_file_path}' not found! Please create it.")
        exit(1)
    except yaml.YAMLError as e:
        logger.critical(f"Error parsing Clash template file '{template_file_path}': {e}")
        exit(1)
    
    clash_config['proxies'] = all_parsed_proxies

    proxy_names = [p['name'] for p in all_parsed_proxies]
    for group in clash_config.get('proxy-groups', []):
        if group['name'] in ['🚀 节点选择', '🔰 Fallback']:
            if group['name'] == '🚀 节点选择':
                group['proxies'] = ['DIRECT'] + proxy_names
            elif group['name'] == '🔰 Fallback':
                group['proxies'] = proxy_names
    
    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')

    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(final_base64_encoded)
    logger.info("Base64 encoded Clash YAML configuration successfully written to base64.txt")

    # --- GitHub Actions 输出 ---
    print(f"::set-output name=total_proxies::{len(all_parsed_proxies)}")
    print(f"::set-output name=successful_proxies::{successful_proxy_count}")
    print(f"::set-output name=processed_urls::{len(successful_urls_this_run)}")


if __name__ == "__main__":
    main()
