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
import ipaddress # 用于 IP 地址验证
import maxminddb # 用于 GeoIP 查找

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# --- GeoIP 相关全局变量 ---
GEOIP_READER = None # 用于存储 maxminddb.Reader 对象
GEOIP_DB_PATH_GLOBAL = None # 用于存储 GeoIP 数据库路径

# --- GeoIP 初始化和查找函数 ---
def init_geoip_reader(db_path):
    """
    初始化 MaxMind GeoIP 数据库读取器.
    """
    global GEOIP_READER, GEOIP_DB_PATH_GLOBAL
    GEOIP_DB_PATH_GLOBAL = db_path
    if not os.path.exists(db_path):
        logger.error(f"GeoIP 数据库文件未找到: {db_path}。GeoIP 过滤将禁用。")
        GEOIP_READER = None
        return False
    try:
        GEOIP_READER = maxminddb.open_database(db_path)
        logger.info(f"成功加载 GeoIP 数据库: {db_path}")
        return True
    except maxminddb.InvalidDatabaseError as e:
        logger.error(f"GeoIP 数据库文件无效或损坏: {db_path} - {e}。GeoIP 过滤将禁用。")
        GEOIP_READER = None
        return False
    except Exception as e:
        logger.error(f"加载 GeoIP 数据库时发生未知错误: {db_path} - {e}。GeoIP 过滤将禁用。")
        GEOIP_READER = None
        return False

def get_country_code(ip_address):
    """
    使用加载的 GeoIP 数据库查找 IP 地址的国家代码.
    返回国家代码 (例如 'CN', 'US')，如果查找失败则返回 None.
    """
    if GEOIP_READER is None:
        return None
    try:
        # 确保 IP 地址是有效的
        ipaddress.ip_address(ip_address)
        record = GEOIP_READER.get(ip_address)
        if record and 'country' in record and 'iso_code' in record['country']:
            return record['country']['iso_code']
        return None
    except ValueError: # 无效的 IP 地址
        return None
    except Exception as e:
        logger.warning(f"GeoIP 查找 IP 地址 '{ip_address}' 时发生错误: {e}")
        return None

# --- 中国节点过滤逻辑 (使用 GeoIP 增强) ---
# 仍然保留关键词，作为 GeoIP 不可用时的备用或补充，或者用于一些特别的名称
CHINA_KEYWORDS = [
    "中国", "china", "cn", "🇨🇳", # 常用关键词
    "ch", "mainland", "domestic", # 其他可能的指示词
    ".cn", ".com.cn", ".net.cn", ".org.cn", # 中国顶级域名
    "aliyun", "tencentcloud", "huaweicloud", # 常见的中国云服务提供商 (可以更具体)
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", # 中国主要城市
    "移动", "联通", "电信", # 运营商关键词
    "cmcc", "unicom", "telecom",
]

def is_likely_china_node(proxy_data):
    """
    检查代理节点是否可能位于中国，优先使用 GeoIP 查找.
    如果 GeoIP 查找失败或未启用，则退回使用关键词判断.
    返回 True 如果它可能在中国，否则返回 False.
    """
    name_lower = proxy_data.get('name', '').lower()
    server = proxy_data.get('server', '')
    server_lower = server.lower()

    # 1. GeoIP 查找 (优先且更准确)
    if GEOIP_READER is not None:
        try:
            # 尝试将主机名解析为 IP 地址
            server_ip = socket.gethostbyname(server)
            country_code = get_country_code(server_ip)
            if country_code == 'CN':
                logger.info(f"  节点 '{proxy_data.get('name')}' (IP: {server_ip}) 经 GeoIP 确认位于中国，已排除。")
                return True
            elif country_code is not None:
                logger.debug(f"  节点 '{proxy_data.get('name')}' (IP: {server_ip}) 位于 {country_code}。")
            else:
                logger.warning(f"  无法通过 GeoIP 确定 IP '{server_ip}' 的国家，尝试关键词匹配。")
        except socket.gaierror:
            logger.warning(f"  无法解析服务器 '{server}' 的 IP，跳过 GeoIP 检查，尝试关键词匹配。")
        except Exception as e:
            logger.error(f"  GeoIP 检查 '{server}' 时发生错误: {e}，尝试关键词匹配。")
    else:
        logger.debug(f"  GeoIP 数据库未加载或初始化失败，将仅依赖关键词过滤。")

    # 2. 关键词检查 (作为补充或 GeoIP 失败时的回退)
    for keyword in CHINA_KEYWORDS:
        if keyword in name_lower or keyword in server_lower:
            logger.info(f"  节点 '{proxy_data.get('name')}' 因关键词 '{keyword}' 被排除。")
            return True

    return False


# --- 代理解析函数 ---
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
    parts.append(str(proxy_data.get('cipher', '')))
    parts.append(str(proxy_data.get('network', '')))
    parts.append(str(proxy_data.get('tls', '')))
    parts.append(str(proxy_data.get('servername', '')))
    parts.append(str(proxy_data.get('ws-path', '')))
    parts.append(str(proxy_data.get('plugin-info', '')))
    parts.append(str(proxy_data.get('alpn', '')))
    parts.append(str(proxy_data.get('flow', ''))) # VLESS flow
    parts.append(str(proxy_data.get('fingerprint', ''))) # TLS fingerprint

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
                    logger.warning(f"Vmess {name}: 无效的 ws-headers 格式，跳过: {config.get('headers')}")

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
                    raise ValueError("格式无效：不是 method:password@server:port 或 method@server:port。")
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
            raise ValueError(f"Base64 解码或正则匹配错误: {decode_err}")
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

# --- 连通性测试函数 ---
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

# --- 获取和解码 URL ---
def fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test=True, enable_china_filter=False):
    all_raw_proxies = [] # 收集所有解析出的代理（包含重复的）
    successful_urls_this_run = set() # 本次运行成功获取的URL

    # 获取要排除的节点服务器列表 (黑名单)
    exclude_servers_str = os.environ.get("EXCLUDE_NODES_BY_SERVER", "")
    exclude_servers = [s.strip().lower() for s in exclude_servers_str.split(',') if s.strip()]

    # 排除一些常见的非代理或无关的 URL 关键词
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
            logger.info(f"跳过非订阅链接 (被关键词过滤): {url}")
            continue

        logger.info(f"[{url_idx+1}/{len(urls)}] 正在处理 URL: {url}")
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
                    logger.info(f"  --- URL: {url} 识别为 YAML 订阅，包含 {len(yaml_proxies)} 个代理。 ---")
                else:
                    json_proxies = try_parse_json_nodes(decoded_content)
                    if json_proxies:
                        current_proxies_from_url.extend(json_proxies)
                        logger.info(f"  --- URL: {url} 识别为 JSON 节点列表，包含 {len(json_proxies)} 个代理。 ---")
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
                                    logger.info(f"  --- URL: {url} Base64 解码成功，识别到 {parsed_line_count} 个代理节点。 ---")
                                else:
                                    logger.warning(f"  --- URL: {url} Base64 解码成功，但内容不匹配已知代理格式。---")
                            except (base64.binascii.Error, UnicodeDecodeError):
                                logger.warning(f"  --- URL: {url} 看起来像 Base64 但解码失败，按纯文本处理。---")

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
                                logger.info(f"  --- URL: {url} 识别为纯文本 {parsed_line_count} 个代理节点。 ---")
                            else:
                                logger.warning(f"  --- URL: {url} 内容未被识别为有效的订阅格式 (UTF-8)。---")

            except UnicodeDecodeError:
                logger.warning(f"  --- URL: {url} UTF-8 解码失败，尝试 Base64 解码。---")
                try:
                    cleaned_content = content.strip()
                    temp_decoded = base64.b64decode(cleaned_content).decode('utf-8')

                    yaml_proxies = try_parse_yaml(temp_decoded)
                    if yaml_proxies:
                        current_proxies_from_url.extend(yaml_proxies)
                        logger.info(f"  --- URL: {url} Base64 解码为 YAML 订阅，包含 {len(yaml_proxies)} 个代理。 ---")
                    else:
                        json_proxies = try_parse_json_nodes(temp_decoded)
                        if json_proxies:
                            current_proxies_from_url.extend(json_proxies)
                            logger.info(f"  --- URL: {url} Base64 解码为 JSON 节点列表，包含 {len(json_proxies)} 个代理。 ---")
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
                                logger.info(f"  --- URL: {url} Base64 解码为 {parsed_line_count} 个代理节点。 ---")
                            else:
                                logger.warning(f"  --- URL: {url} Base64 解码成功，但内容不匹配已知代理格式。---")

                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    logger.error(f"  --- URL: {url} Base64 解码或 UTF-8 转换失败: {decode_err} ---")
                    # 尝试用 latin-1 解码，作为最后手段，尽管可能丢失信息
                    content.decode('latin-1', errors='ignore')
                    logger.warning(f"警告：无法将 {url} 的内容解码为 UTF-8 或 Base64。将使用 latin-1 且忽略错误。")

            if current_proxies_from_url:
                all_raw_proxies.extend(current_proxies_from_url)
                successful_urls_this_run.add(url) # 标记此URL本次成功下载和解析

        except requests.exceptions.RequestException as e:
            logger.error(f"从 URL 获取数据失败: {url}，原因: {e}")
        except Exception as e:
            logger.error(f"处理 URL {url} 时发生意外错误: {e}")

    # --- 去重和连通性测试 (并行化) ---
    unique_proxies_for_test = {}
    for proxy_dict in all_raw_proxies:
        if proxy_dict:
            # 检查黑名单
            server_to_check = str(proxy_dict.get('server', '')).lower()
            if any(s in server_to_check for s in exclude_servers):
                logger.info(f"跳过代理 {proxy_dict.get('name', 'unknown')} (服务器: {server_to_check})，因为它在黑名单中。")
                continue

            # 新增：检查是否是中国节点 (使用 GeoIP 增强)
            if enable_china_filter and is_likely_china_node(proxy_dict):
                # is_likely_china_node 内部会打印详细的排除原因
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
                        # 确保 ping 值是整数，避免小数显示
                        proxy_dict['name'] = f"{base_name}-{generate_proxy_fingerprint(proxy_dict)[:8]} (Ping: {int(latency*1000)}ms)"
                        final_filtered_proxies.append(proxy_dict)
                        successful_proxy_count += 1
                    else:
                        pass # 连接失败的节点不会被添加到最终列表
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

# --- GitHub API 辅助函数 ---
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
        logger.error(f"从 GitHub 获取文件出错 (HTTP 错误): {http_err}。响应: {response.text[:200] if response else 'N/A'}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"从 GitHub 获取文件出错 (请求错误): {req_err}")
        return None, None
    except Exception as e:
        logger.error(f"从 GitHub 获取文件出错 (其他错误): {e}")
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
        logger.info(f"成功更新 GitHub 上的 {file_path}。")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"更新 GitHub 文件出错: {e}。响应: {response.text[:200] if response else 'N/A'}")
        if response and response.status_code == 409:
            logger.warning("冲突：提交前 GitHub 上的文件内容已更改。请重新运行。")
        return False

# --- 主函数 ---
def main():
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    template_file_path = os.environ.get("CLASH_TEMPLATE_PATH", "clash_template.yml")
    # 从环境变量获取 GeoIP 数据库路径，默认为 "clash/Country.mmdb"
    geoip_db_path_env = os.environ.get("GEOIP_DB_PATH", "clash/Country.mmdb")

    # 尝试初始化 GeoIP Reader
    logger.info(f"尝试初始化 GeoIP 数据库，路径: {geoip_db_path_env}")
    init_geoip_reader(geoip_db_path_env)


    try:
        parts = url_list_repo_api.split('/')
        if len(parts) < 8 or parts[2] != 'api.github.com' or parts[3] != 'repos' or parts[6] != 'contents':
            raise ValueError("URL_LIST_REPO_API 看起来不是有效的 GitHub Content API URL。")

        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except ValueError as ve:
        logger.error(f"错误: {ve}")
        logger.error("请确保 URL_LIST_REPO_API 正确设置为 GitHub Content API URL (例如：https://api.github.com/repos/user/repo/contents/path/to/file.txt)。")
        exit(1)
    except IndexError:
        logger.error("错误: URL_LIST_REPO_API 格式不正确或不完整。无法提取所有者、仓库或文件路径。")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        logger.error("错误: 环境变量 BOT 或 URL_LIST_REPO_API 未设置！")
        logger.error("请确保您已在 GitHub Actions secrets/variables 中正确设置这些变量。")
        exit(1)

    # 获取 URL 列表和它的 SHA
    logger.info("正在从 GitHub 获取 URL 列表及其 SHA...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        logger.error("无法获取 URL 列表或其 SHA，脚本终止。")
        exit(1)

    original_urls = set(url_content.strip().split('\n'))
    logger.info(f"从 GitHub 获取到 {len(original_urls)} 个订阅 URL。")

    enable_connectivity_test = os.environ.get("ENABLE_CONNECTIVITY_TEST", "true").lower() == "true"
    enable_china_filter = os.environ.get("EXCLUDE_CHINA_NODES", "false").lower() == "true"

    # 执行代理抓取、解析、去重和测试，并传入是否启用中国节点过滤
    # is_likely_china_node 函数现在内部会使用 GEOIP_READER
    all_parsed_proxies, successful_urls_this_run, successful_proxy_count = \
        fetch_and_decode_urls_to_clash_proxies(list(original_urls), enable_connectivity_test, enable_china_filter)

    # --- 处理 URL 列表的更新 ---
    failed_urls_file = "failed_urls.json"
    failed_urls_tracking = {}
    if os.path.exists(failed_urls_file):
        try:
            with open(failed_urls_file, "r") as f:
                failed_urls_tracking = json.load(f)
            logger.info(f"已从 {failed_urls_file} 加载失败 URL 跟踪记录。")
        except json.JSONDecodeError:
            logger.warning(f"无法解码 {failed_urls_file}，将从空的跟踪记录开始。")

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
                logger.warning(f"URL '{url}' 获取/解析失败 (计数: {failed_urls_tracking[url]})。暂时保留。")
            else:
                logger.error(f"URL '{url}' 失败 {failed_urls_tracking[url]} 次，将从列表中移除。")

    with open(failed_urls_file, "w") as f:
        json.dump(failed_urls_tracking, f)
    logger.info(f"更新后的失败 URL 跟踪记录已保存到 {failed_urls_file}。")

    new_url_list_content = "\n".join(sorted(list(new_urls_for_repo)))

    if new_url_list_content.strip() != url_content.strip():
        logger.info("正在更新 GitHub url.txt 文件...")
        commit_message = "feat: 通过 GitHub Actions 更新有效订阅链接 (自动过滤)"
        update_success = update_github_file_content(
            repo_contents_api_base,
            bot_token,
            file_path_in_repo,
            new_url_list_content,
            url_file_sha,
            commit_message
        )
        if update_success:
            logger.info("url.txt 文件更新成功。")
        else:
            logger.error("url.txt 文件更新失败。")
    else:
        logger.info("url.txt 文件内容未更改，无需更新。")

    # --- 构建 Clash 完整配置 ---
    clash_config = {}
    try:
        with open(template_file_path, 'r', encoding='utf-8') as f:
            clash_config = yaml.safe_load(f)
        logger.info(f"已从 {template_file_path} 加载 Clash 配置模板。")
    except FileNotFoundError:
        logger.critical(f"未找到 Clash 模板文件 '{template_file_path}'！请创建它。")
        exit(1)
    except yaml.YAMLError as e:
        logger.critical(f"解析 Clash 模板文件 '{template_file_path}' 时出错: {e}")
        exit(1)

    clash_config['proxies'] = all_parsed_proxies

    # 根据 Clash 配置中的 proxy-groups 动态添加节点
    proxy_names = [p['name'] for p in all_parsed_proxies]
    for group in clash_config.get('proxy-groups', []):
        # 假设你的节点选择组叫 '🚀 节点选择' 和 '🔰 Fallback'
        if group['name'] == '🚀 节点选择':
            group['proxies'] = ['DIRECT'] + proxy_names # 通常节点选择组会包含 DIRECT
        elif group['name'] == '🔰 Fallback':
            group['proxies'] = proxy_names # Fallback 组通常只包含代理节点
        # 你可以根据你的模板文件中的实际组名称进行调整

    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    # 1. 输出 Clash YAML 到根目录/base64.yaml
    with open("base64.yaml", "w", encoding="utf-8") as f:
        f.write(final_clash_yaml)
    logger.info("Clash YAML 配置已成功写入 base64.yaml。")

    # 2. 输出 Base64 编码的 Clash YAML 到根目录/base64.txt
    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')
    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(final_base64_encoded)
    logger.info("Base64 编码的 Clash YAML 配置已成功写入 base64.txt。")


    # --- GitHub Actions 输出 ---
    print(f"::set-output name=total_proxies::{len(all_parsed_proxies)}")
    print(f"::set-output name=successful_proxies::{successful_proxy_count}")
    print(f"::set-output name=processed_urls::{len(successful_urls_this_run)}")


if __name__ == "__main__":
    main()
