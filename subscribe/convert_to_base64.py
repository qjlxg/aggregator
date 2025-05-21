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

# --- Proxy Parsing Functions ---
def generate_proxy_fingerprint(proxy_data):
    """
    根据代理的关键连接信息生成一个唯一的哈希指纹。
    这用于识别和去重相同的代理，即使它们的名称不同。
    """
    parts = []
    # 尽可能包含所有核心连接参数
    parts.append(proxy_data.get('type', ''))
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
                proxy['ws-headers'] = str(config.get('headers'))

        return proxy
    except Exception as e:
        print(f"解析 Vmess 链接失败: {vmess_url[:50]}...，原因: {e}")
        return None

def parse_trojan(trojan_url):
    try:
        parsed = urlparse(trojan_url)
        password = parsed.username
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"Trojan-{server}"

        params = parse_qs(parsed.query)
        tls = True
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

        return proxy
    except Exception as e:
        print(f"解析 Trojan 链接失败: {trojan_url[:50]}...，原因: {e}")
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

        missing_padding = len(encoded_part) % 4
        if missing_padding:
            encoded_part += '=' * (4 - missing_padding)
        
        try:
            # 尝试使用 utf-8 解码，如果失败则尝试 latin-1
            decoded_bytes = base64.urlsafe_b64decode(encoded_part)
            try:
                decoded_str = decoded_bytes.decode('utf-8')
            except UnicodeDecodeError:
                decoded_str = decoded_bytes.decode('latin-1', errors='ignore')
                print(f"    Warning: Shadowsocks link decoded to non-UTF-8 characters, using latin-1 for {ss_url[:50]}...")
            
            # 关键修改：只取第一个 '@' 之前和之后的部分，忽略所有后续内容
            parts = decoded_str.split('@', 1) # 只分割一次
            
            if len(parts) != 2:
                raise ValueError(f"Invalid format after base64 decoding: Missing '@' separator or incorrect structure.")

            method_password = parts[0]
            server_port_and_tail = parts[1] # 包含服务器和端口，以及可能存在的后续乱码

            # 进一步清理 server_port_and_tail，只保留有效的服务器:端口部分
            # 正则表达式匹配：
            # ^                  - 字符串开头
            # [\w\d\.\-]+       - 匹配一个或多个单词字符（字母、数字、下划线）、数字、点或连字符（用于服务器名）
            # :                  - 匹配冒号
            # \d+                - 匹配一个或多个数字（端口号）
            clean_server_port_match = re.match(r'^[\w\d\.\-]+\:\d+', server_port_and_tail)
            if clean_server_port_match:
                server_port_str = clean_server_port_match.group(0)
            else:
                raise ValueError(f"Invalid server:port format in: '{server_port_and_tail}'")

            method_password_parts = method_password.split(':', 1)
            if len(method_password_parts) != 2:
                raise ValueError(f"Invalid method:password format: '{method_password}'")
            method = method_password_parts[0]
            password = method_password_parts[1]

            server_port_parts = server_port_str.split(':')
            if len(server_port_parts) != 2:
                raise ValueError(f"Invalid server:port format: '{server_port_str}'")
            server = server_port_parts[0]
            port = int(server_port_parts[1])

            proxy = {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': port,
                'cipher': method,
                'password': password,
            }

            if plugin_info_str:
                proxy['plugin-info'] = plugin_info_str

            return proxy
        except (base64.binascii.Error) as b64_err:
            raise ValueError(f"Base64 decoding error: {b64_err}")
    except Exception as e:
        print(f"解析 Shadowsocks 链接失败: {ss_url[:100]}...，原因: {e}")
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

        proxy = {
            'name': name,
            'type': 'hysteria2',
            'server': server,
            'port': port,
            'password': uuid,
            'tls': tls,
            'skip-cert-verify': skip_cert_verify,
            'fast-open': fast_open,
        }
        if servername:
            proxy['servername'] = servername
        if params.get('alpn'):
            proxy['alpn'] = ','.join(params['alpn'])

        return proxy
    except Exception as e:
        print(f"解析 Hysteria2 链接失败: {hy2_url[:50]}...，原因: {e}")
        return None

# --- Connectivity Test Function ---
def test_tcp_connectivity(server, port, timeout=3, retries=2, delay=1):
    """
    尝试与指定的服务器和端口建立TCP连接，测试连通性。
    增加重试机制，以应对瞬时网络抖动或服务器短暂问题。
    返回 True 如果连接成功，否则返回 False。
    """
    for i in range(retries + 1): # retries + 1 = 第一次尝试 + 重试次数
        try:
            sock = socket.create_connection((server, port), timeout=timeout)
            sock.close()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print(f"    连接尝试 {i+1}/{retries+1} 失败 for {server}:{port} - {e}")
            if i < retries: # 如果不是最后一次尝试，则等待并重试
                time.sleep(delay)
        except Exception as e:
            print(f"  TCP连接测试发生未知错误: {server}:{port} - {e}")
            return False
    return False # 所有重试都失败

# --- Fetch and Decode URLs (Modified for deduplication and naming) ---
def fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test=True):
    unique_proxies = {}
    successful_urls = set()

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

    for url in urls:
        url = url.strip()
        if not url:
            continue

        if any(keyword in url for keyword in EXCLUDE_KEYWORDS):
            print(f"Skipping non-subscription link (filtered by keyword): {url}")
            continue

        print(f"Processing URL: {url}")
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            content = response.content

            print(f"  --- URL: {url} Downloaded content size: {len(content)} bytes ---")

            decoded_content = ""
            current_proxies = []

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
                        return [parse_vmess(f"vmess://{base64.b64encode(json.dumps(node).encode('utf-8')).decode('utf-8')}") for node in data]
                    return None
                except json.JSONDecodeError:
                    return None

            try:
                decoded_content = content.decode('utf-8')
                print(f"  --- URL: {url} Successfully decoded to UTF-8 ---")

                yaml_proxies = try_parse_yaml(decoded_content)
                if yaml_proxies:
                    current_proxies.extend(yaml_proxies)
                    print(f"  --- URL: {url} Identified as YAML subscription ---")
                else:
                    json_proxies = try_parse_json_nodes(decoded_content)
                    if json_proxies:
                        current_proxies.extend(json_proxies)
                        print(f"  --- URL: {url} Identified as JSON node list ---")
                    else:
                        # 尝试 Base64 解码，即使是 UTF-8 也能处理 Base64 编码的订阅
                        if len(decoded_content.strip()) > 0 and len(decoded_content.strip()) % 4 == 0 and re.fullmatch(r'[A-Za-z0-9+/=]*', decoded_content.strip()):
                            try:
                                temp_decoded = base64.b64decode(decoded_content.strip()).decode('utf-8')
                                lines = temp_decoded.split('\n')
                                parsed_line_count = 0
                                for line in lines:
                                    line = line.strip()
                                    if line.startswith("vmess://"):
                                        p = parse_vmess(line)
                                        if p: current_proxies.append(p); parsed_line_count += 1
                                    elif line.startswith("trojan://"):
                                        p = parse_trojan(line)
                                        if p: current_proxies.append(p); parsed_line_count += 1
                                    elif line.startswith("ss://"):
                                        p = parse_shadowsocks(line)
                                        if p: current_proxies.append(p); parsed_line_count += 1
                                    elif line.startswith("hysteria2://"):
                                        p = parse_hysteria2(line)
                                        if p: current_proxies.append(p); parsed_line_count += 1
                                if parsed_line_count > 0:
                                    print(f"  --- URL: {url} Base64 decoded and identified {parsed_line_count} proxy nodes ---")
                                else:
                                    print(f"  --- URL: {url} Base64 decoded successfully, but content doesn't match known proxy format.---")
                            except (base64.binascii.Error, UnicodeDecodeError):
                                print(f"  --- URL: {url} Looks like Base64 but failed to decode, treating as plaintext.---")

                        if not current_proxies: # 如果 Base64 解码或之前的解析没有得到代理，尝试直接解析为纯文本链接
                            lines = decoded_content.split('\n')
                            parsed_line_count = 0
                            for line in lines:
                                line = line.strip()
                                if line.startswith("vmess://"):
                                    p = parse_vmess(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("trojan://"):
                                    p = parse_trojan(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("ss://"):
                                    p = parse_shadowsocks(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("hysteria2://"):
                                    p = parse_hysteria2(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                            if parsed_line_count > 0:
                                print(f"  --- URL: {url} Identified as plaintext {parsed_line_count} proxy nodes ---")
                            else:
                                print(f"  --- URL: {url} Content not identified as valid subscription format (UTF-8).---")

            except UnicodeDecodeError: # 如果直接 UTF-8 解码失败，再尝试 Base64 解码
                print(f"  --- URL: {url} UTF-8 decoding failed, trying Base64 decoding.---")
                try:
                    cleaned_content = content.strip()
                    temp_decoded = base64.b64decode(cleaned_content).decode('utf-8')
                    print(f"  --- URL: {url} Successfully decoded Base64 content to UTF-8 ---")

                    yaml_proxies = try_parse_yaml(temp_decoded)
                    if yaml_proxies:
                        current_proxies.extend(yaml_proxies)
                        print(f"  --- URL: {url} Base64 decoded to YAML subscription ---")
                    else:
                        json_proxies = try_parse_json_nodes(temp_decoded)
                        if json_proxies:
                            current_proxies.extend(json_proxies)
                            print(f"  --- URL: {url} Base64 decoded to JSON node list ---")
                        else:
                            lines = temp_decoded.split('\n')
                            parsed_line_count = 0
                            for line in lines:
                                line = line.strip()
                                if line.startswith("vmess://"):
                                    p = parse_vmess(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("trojan://"):
                                    p = parse_trojan(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("ss://"):
                                    p = parse_shadowsocks(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                                elif line.startswith("hysteria2://"):
                                    p = parse_hysteria2(line)
                                    if p: current_proxies.append(p); parsed_line_count += 1
                            if parsed_line_count > 0:
                                print(f"  --- URL: {url} Base64 decoded to {parsed_line_count} proxy nodes ---")
                            else:
                                print(f"  --- URL: {url} Base64 decoded successfully, but content doesn't match known proxy format.---")

                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    print(f"  --- URL: {url} Base64 decoding or UTF-8 conversion failed: {decode_err} ---")
                    # Fallback to latin-1 for content that can't be decoded to UTF-8 or Base64 (for logging purposes)
                    content.decode('latin-1', errors='ignore') 
                    print(f"Warning: Could not decode content from {url} to UTF-8 or Base64. Using latin-1 and ignoring errors.")

            # --- Deduplication, Name Standardization, and Connectivity Test Logic ---
            for proxy_dict in current_proxies:
                if not proxy_dict:
                    continue

                fingerprint = generate_proxy_fingerprint(proxy_dict)

                if fingerprint not in unique_proxies:
                    server = proxy_dict.get('server')
                    port = proxy_dict.get('port')

                    if enable_connectivity_test and server and isinstance(port, int):
                        print(f"    正在测试连通性: {server}:{port} ...")
                        if not test_tcp_connectivity(server, port): # 使用带重试的连通性测试
                            print(f"    节点不可达（多次尝试后），跳过: {server}:{port}")
                            continue
                        else:
                            print(f"    节点可达: {server}:{port}")
                    else:
                        print(f"    跳过连通性测试 (未启用或信息不全): {server}:{port}")

                    base_name = f"{proxy_dict.get('type', 'unknown').upper()}-{proxy_dict.get('server', 'unknown')}"
                    proxy_dict['name'] = f"{base_name}-{fingerprint[:8]}"
                    unique_proxies[fingerprint] = proxy_dict
                    print(f"    添加新代理: {proxy_dict['name']}")
                else:
                    print(f"    跳过重复代理 (指纹: {fingerprint})")

            if current_proxies:
                successful_urls.add(url)

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch data from URL: {url}, reason: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing URL {url}: {e}")

    final_proxies_list = list(unique_proxies.values())
    print(f"Successfully parsed, deduplicated, tested, and aggregated {len(final_proxies_list)} unique and reachable proxy nodes.")
    return final_proxies_list, list(successful_urls)

# --- GitHub API Helpers (Modified to check ETag if X-GitHub-Sha is missing) ---
def get_github_file_content(api_url, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    try:
        print(f"DEBUG: 尝试从 GitHub API 获取文件: {api_url}")
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        # 打印所有响应头
        print("DEBUG: GitHub API 响应头:")
        for header, value in response.headers.items():
            print(f"  {header}: {value}")
            
        print(f"DEBUG: GitHub API 响应状态码: {response.status_code}")
        
        # 优先从 X-GitHub-Sha 获取 SHA，如果不存在，则尝试从 ETag 获取
        sha = response.headers.get("X-GitHub-Sha")
        if sha is None:
            etag = response.headers.get("ETag")
            if etag:
                # ETag 值通常是带引号的，我们需要去除引号
                sha = etag.strip('"')
                print(f"DEBUG: X-GitHub-Sha 为 None，从 ETag 获取到 SHA: {sha}")
            else:
                print("DEBUG: 既未获取到 X-GitHub-Sha，也未获取到 ETag。")
        else:
            print(f"DEBUG: 从 X-GitHub-Sha 获取到 SHA: {sha}")
        
        response.raise_for_status()
        
        print("DEBUG: GitHub API 响应内容片段 (前500字符):")
        print(response.text[:500])
        
        return response.text, sha
    except requests.exceptions.HTTPError as http_err:
        print(f"Error fetching file from GitHub (HTTP Error): {http_err}")
        if response is not None:
            print(f"DEBUG: 错误响应内容: {response.text}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        print(f"Error fetching file from GitHub (Request Error): {req_err}")
        return None, None
    except Exception as e:
        print(f"Error fetching file from GitHub (Other Error): {e}")
        return None, None

def update_github_file_content(repo_contents_api_base, token, file_path, new_content, sha, commit_message):
    url = f"{repo_contents_api_base}/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
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
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error updating file on GitHub: {e}")
        if response and response.status_code == 409:
            print("Conflict: File content changed on GitHub before commit. Please re-run.")
        return False

# --- Main Function ---
def main():
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")

    try:
        # 确保 url_list_repo_api 是一个完整的 GitHub Content API URL
        # 例如: https://api.github.com/repos/owner/repo/contents/path/to/file.txt
        parts = url_list_repo_api.split('/')
        if len(parts) < 8 or parts[2] != 'api.github.com' or parts[3] != 'repos' or parts[6] != 'contents':
            raise ValueError("URL_LIST_REPO_API does not seem to be a valid GitHub Content API URL.")
            
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:]) # 'contents' 之后的路径
    except ValueError as ve:
        print(f"Error: {ve}")
        print("Please ensure URL_LIST_REPO_API is correctly set to a GitHub Content API URL (e.g., https://api.github.com/repos/user/repo/contents/path/to/file.txt).")
        exit(1)
    except IndexError:
        print("Error: URL_LIST_REPO_API format is incorrect or incomplete. Cannot extract owner, repo, or file path.")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        print("Error: Environment variables BOT or URL_LIST_REPO_API are not set!")
        print("Please ensure you've correctly set these variables in GitHub Actions secrets/variables.")
        exit(1)

    print("Fetching URL list and its SHA from GitHub...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        print("Could not get URL list or its SHA, script terminated.")
        exit(1)

    urls = url_content.strip().split('\n')
    print(f"Fetched {len(urls)} subscription URLs from GitHub.")

    enable_connectivity_test = os.environ.get("ENABLE_CONNECTIVITY_TEST", "true").lower() == "true"


    all_parsed_proxies, successful_urls = fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test)

    # 构建 Clash 完整配置
    clash_config = {
        'port': 7890,
        'socks-port': 7891,
        'redir-port': 7892,
        'tproxy-port': 7893,
        'mixed-port': 7890,
        'mode': 'rule',
        'log-level': 'info',
        'allow-lan': True,
        'bind-address': '*',
        'external-controller': '127.0.0.1:9090',
        'dns': {
            'enable': True,
            'ipv6': False,
            'enhanced-mode': 'fake-ip',
            'listen': '0.0.0.0:53',
            'default-nameserver': [
                '114.114.114.114',
                '8.8.8.8'
            ],
            'nameserver': [
                'https://dns.google/dns-query',
                'tls://dns.google'
            ],
            'fallback': [
                'tls://1.1.1.1',
                'tcp://8.8.4.4',
                'https://dns.opendns.com/dns-query'
            ],
            'fallback-filter': {
                'geoip': True,
                'geoip-code': 'CN',
                'ipcidr': [
                    '240.0.0.0/4'
                ]
            }
        },
        'proxies': all_parsed_proxies,

        'proxy-groups': [
            {
                'name': '🚀 节点选择',
                'type': 'select',
                'proxies': ['DIRECT'] + [p['name'] for p in all_parsed_proxies]
            },
            {
                'name': '📲 国外媒体',
                'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT']
            },
            {
                'name': '🤖 AI/ChatGPT',
                'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT']
            },
            {
                'name': '🌍 其他流量',
                'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT']
            },
            {
                'name': '🐟 漏网之鱼',
                'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT']
            },
            {
                'name': '🛑 广告拦截',
                'type': 'select',
                'proxies': ['REJECT', 'DIRECT']
            },
            {
                'name': '🔰 Fallback',
                'type': 'fallback',
                'proxies': [p['name'] for p in all_parsed_proxies],
                'url': 'http://www.google.com/generate_204',
                'interval': 300
            }
        ],
        'rules': [
            'DOMAIN-KEYWORD,openai,🤖 AI/ChatGPT',
            'DOMAIN-KEYWORD,google,📲 国外媒体',
            'DOMAIN-KEYWORD,youtube,📲 国外媒体',
            'DOMAIN-KEYWORD,netflix,📲 国外媒体',
            'DOMAIN-KEYWORD,github,🌍 其他流量',
            'DOMAIN-SUFFIX,cn,DIRECT',
            'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve',
            'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
            'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,127.0.0.1/8,DIRECT,no-resolve',
            'GEOIP,CN,DIRECT,no-resolve',
            'MATCH,🐟 漏网之鱼'
        ]
    }

    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')

    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(final_base64_encoded)
    print("Base64 encoded Clash YAML configuration successfully written to base64.txt")

    new_url_list_content = "\n".join(sorted(list(set(successful_urls))))

    if new_url_list_content.strip() != url_content.strip():
        print("Updating GitHub url.txt file...")
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
            print("url.txt file updated successfully.")
        else:
            print("Failed to update url.txt file.")
    else:
        print("url.txt file content unchanged, no update needed.")

if __name__ == "__main__":
    main()
