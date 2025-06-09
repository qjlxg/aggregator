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

# --- Global Constants ---
MAX_WORKERS_CONNECTIVITY_TEST = 30
EXCLUDE_KEYWORDS = [
    "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
    "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net",
    "t.me", "api.w.org",
]

# --- Proxy Parsing Functions ---
def generate_proxy_fingerprint(proxy_data):
    """
    根据代理的核心连接信息生成一个唯一的哈希指纹。
    确保所有字段都转换为字符串以避免 TypeError。
    """
    try:
        p_type = str(proxy_data.get('type', '')).lower()
        server = str(proxy_data.get('server', ''))
        port = str(proxy_data.get('port', ''))

        fingerprint_parts = [p_type, server, port]

        if p_type == 'vmess':
            fingerprint_parts.append(str(proxy_data.get('uuid', '')))
            fingerprint_parts.append(str(proxy_data.get('alterId', '')))
        elif p_type == 'trojan':
            fingerprint_parts.append(str(proxy_data.get('password', '')))
        elif p_type == 'ss':
            fingerprint_parts.append(str(proxy_data.get('password', '')))
            fingerprint_parts.append(str(proxy_data.get('cipher', '')))
        elif p_type == 'hysteria2':
            fingerprint_parts.append(str(proxy_data.get('password', '')))

        # 调试日志：检查非字符串元素
        if not all(isinstance(x, str) for x in fingerprint_parts):
            print(f"Debug: Non-string elements in fingerprint_parts: {fingerprint_parts}, proxy_dict: {proxy_data}")

        unique_string = "_".join(fingerprint_parts)
        return hashlib.md5(unique_string.encode('utf-8')).hexdigest()
    except Exception as e:
        print(f"Error generating fingerprint for proxy: {proxy_data}, reason: {e}")
        return None

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
        skip_cert_verify = config.get('skip-cert-verify', False)  # 修复：明确定义

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
            'server': server,  # 修复：确保正确闭合
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
            decoded_bytes = base64.urlsafe_b64decode(encoded_part)
            try:
                decoded_str = decoded_bytes.decode('utf-8')
            except UnicodeDecodeError:
                decoded_str = decoded_bytes.decode('latin-1', errors='ignore')
                print(f"    Warning: Shadowsocks link decoded to non-UTF-8 characters, using latin-1 for {ss_url[:50]}...")

            parts = decoded_str.split('@', 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid format after base64 decoding: Missing '@' separator or incorrect structure.")

            method_password = parts[0]
            method_password_parts = method_password.split(':', 1)
            if len(method_password_parts) != 2:
                raise ValueError(f"Invalid method:password format: '{method_password}'")
            method = method_password_parts[0]
            password = method_password_parts[1]

            server_port_and_tail = parts[1]
            clean_server_port_match = re.match(r'^[\w\d\.\-]+\:(\d+)', server_port_and_tail)
            if clean_server_port_match:
                server = server_port_and_tail.split(':')[0]
                port = int(clean_server_port_match.group(1))
            else:
                raise ValueError(f"Invalid server:port format in: '{server_port_and_tail}'")

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
        except base64.binascii.Error as b64_err:
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
def test_tcp_connectivity(server, port, timeout=1, retries=1, delay=0.5):
    for i in range(retries + 1):
        try:
            sock = socket.create_connection((server, int(port)), timeout=timeout)
            sock.close()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError, ValueError) as e:
            if i < retries:
                time.sleep(delay)
        except Exception as e:
            print(f"Debug: Unexpected error during TCP connect to {server}:{port}: {e}")
            return False
    return False

# --- Subscription Parsing Helper Functions ---
def _parse_single_proxy_link(line):
    """Helper function to parse a single proxy link string."""
    line = line.strip()
    if line.startswith("vmess://"):
        return parse_vmess(line)
    elif line.startswith("trojan://"):
        return parse_trojan(line)
    elif line.startswith("ss://"):
        return parse_shadowsocks(line)
    elif line.startswith("hysteria2://"):
        return parse_hysteria2(line)
    return None

def _try_parse_yaml_proxies(text):
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and 'proxies' in data and isinstance(data['proxies'], list):
            return data['proxies']
        elif isinstance(data, list) and all(isinstance(item, dict) and 'type' in item for item in data):
            return data
        return None
    except yaml.YAMLError:
        return None

def _try_parse_v2rayn_json_proxies(text):
    try:
        data = json.loads(text)
        if isinstance(data, list) and all(isinstance(item, dict) and 'v' in item and 'ps' in item for item in data):
            parsed_list = []
            for node in data:
                vmess_link = f"vmess://{base64.b64encode(json.dumps(node).encode('utf-8')).decode('utf-8')}"
                p = parse_vmess(vmess_link)
                if p:
                    parsed_list.append(p)
            return parsed_list
        return None
    except json.JSONDecodeError:
        return None

def _parse_proxies_from_decoded_text(decoded_text, url_for_logging):
    """
    Tries to parse proxies from decoded text content.
    Attempts YAML, then V2RayN JSON, then line-by-line.
    Returns a list of parsed proxy dicts, or an empty list if none found.
    """
    proxies = []

    yaml_proxies = _try_parse_yaml_proxies(decoded_text)
    if yaml_proxies:
        print(f"  --- URL: {url_for_logging} Identified as YAML subscription, found {len(yaml_proxies)} proxies ---")
        return yaml_proxies

    json_node_proxies = _try_parse_v2rayn_json_proxies(decoded_text)
    if json_node_proxies:
        print(f"  --- URL: {url_for_logging} Identified as V2RayN JSON node list, found {len(json_node_proxies)} proxies ---")
        return json_node_proxies

    lines = decoded_text.split('\n')
    parsed_line_count = 0
    for line in lines:
        proxy = _parse_single_proxy_link(line)
        if proxy:
            proxies.append(proxy)
            parsed_line_count += 1

    if parsed_line_count > 0:
        print(f"  --- URL: {url_for_logging} Identified as plaintext, {parsed_line_count} proxy nodes parsed ---")
    return proxies

# --- Fetch and Decode URLs ---
def fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test=True):
    all_raw_proxies = []
    successful_urls = set()

    for url_idx, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue

        if any(keyword in url for keyword in EXCLUDE_KEYWORDS):
            print(f"Skipping non-subscription link (filtered by keyword): {url}")
            continue

        print(f"Processing URL ({url_idx + 1}/{len(urls)}): {url}")
        current_proxies_from_url = []

        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            content = response.content
            print(f"  --- URL: {url} Downloaded content size: {len(content)} bytes ---")

            decoded_successfully = False
            try:
                decoded_content_utf8 = content.decode('utf-8')
                decoded_successfully = True

                proxies_from_utf8 = _parse_proxies_from_decoded_text(decoded_content_utf8, url)
                if proxies_from_utf8:
                    current_proxies_from_url.extend(proxies_from_utf8)
                else:
                    stripped_content = decoded_content_utf8.strip()
                    if len(stripped_content) > 0 and (len(stripped_content) % 4 == 0 or '=' not in stripped_content) and re.fullmatch(r'[A-Za-z0-9+/=]*', stripped_content):
                        try:
                            missing_padding = len(stripped_content) % 4
                            if missing_padding:
                                stripped_content += '=' * (4 - missing_padding)

                            decoded_from_base64_in_utf8 = base64.b64decode(stripped_content).decode('utf-8')
                            print(f"  --- URL: {url} Content (originally UTF-8) was Base64, re-decoding and parsing ---")
                            proxies_from_b64_in_utf8 = _parse_proxies_from_decoded_text(decoded_from_base64_in_utf8, url)
                            if proxies_from_b64_in_utf8:
                                current_proxies_from_url.extend(proxies_from_b64_in_utf8)
                        except (base64.binascii.Error, UnicodeDecodeError) as e_b64_utf8:
                            print(f"  --- URL: {url} Looked like Base64 (in UTF-8 text) but failed to decode/parse: {e_b64_utf8} ---")
                        except Exception as e_generic_b64_utf8:
                            print(f"  --- URL: {url} Unexpected error during Base64 (in UTF-8 text) processing: {e_generic_b64_utf8} ---")
            except UnicodeDecodeError:
                print(f"  --- URL: {url} UTF-8 decoding failed. Will try direct Base64. ---")

            if not current_proxies_from_url:
                try:
                    cleaned_byte_content = content.strip()
                    try:
                        b64_text_equivalent = cleaned_byte_content.decode('ascii')
                    except UnicodeDecodeError:
                        b64_text_equivalent = cleaned_byte_content.decode('latin-1', errors='ignore')

                    missing_padding = len(b64_text_equivalent) % 4
                    if missing_padding:
                        cleaned_byte_content += b'=' * (4 - missing_padding)

                    decoded_content_b64 = base64.b64decode(cleaned_byte_content).decode('utf-8')
                    proxies_from_b64 = _parse_proxies_from_decoded_text(decoded_content_b64, url)
                    if proxies_from_b64:
                        current_proxies_from_url.extend(proxies_from_b64)
                except (base64.binascii.Error, UnicodeDecodeError) as b64_err:
                    if not decoded_successfully:
                        print(f"  --- URL: {url} Direct Base64 decoding or subsequent UTF-8 conversion failed: {b64_err} ---")
                except Exception as e_b64_direct:
                    print(f"  --- URL: {url} Unexpected error during direct Base64 processing: {e_b64_direct} ---")

            if current_proxies_from_url:
                all_raw_proxies.extend(current_proxies_from_url)
                successful_urls.add(url)
                print(f"  +++ URL: {url} Successfully parsed {len(current_proxies_from_url)} proxies. +++")
            else:
                content_snippet = content[:100].decode('latin-1', errors='ignore')
                print(f"  --- URL: {url} No proxies successfully parsed from this URL. Content snippet (latin-1, first 100 chars): '{content_snippet}' ---")

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch data from URL: {url}, reason: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing URL {url}: {e}")

    # --- Deduplication and Connectivity Test (Parallelized) ---
    unique_proxies_for_test = {}
    for proxy_dict in all_raw_proxies:
        if not proxy_dict or not isinstance(proxy_dict, dict) or 'server' not in proxy_dict or 'port' not in proxy_dict:
            print(f"Warning: Skipping invalid proxy data: {proxy_dict}")
            continue
        fingerprint = generate_proxy_fingerprint(proxy_dict)
        if fingerprint:
            unique_proxies_for_test[fingerprint] = proxy_dict

    proxies_to_test_list = list(unique_proxies_for_test.values())
    final_filtered_proxies = []

    if enable_connectivity_test:
        print(f"\n开始并行连通性测试，共 {len(proxies_to_test_list)} 个唯一代理...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_CONNECTIVITY_TEST) as executor:
            future_to_proxy = {
                executor.submit(test_tcp_connectivity, p['server'], p['port']): p
                for p in proxies_to_test_list if p.get('server') and p.get('port') is not None
            }
            processed_count = 0
            total_testable_proxies = len(future_to_proxy)

            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy_dict = future_to_proxy[future]
                server = proxy_dict.get('server')
                port = proxy_dict.get('port')
                processed_count += 1
                try:
                    is_reachable = future.result()
                    if is_reachable:
                        original_name = proxy_dict.get('name', f"{proxy_dict.get('type', 'UNKNOWN').upper()}-{proxy_dict.get('server', 'unknown')}")
                        short_fingerprint = generate_proxy_fingerprint(proxy_dict)[:6]
                        max_name_len = 50

                        if len(original_name) > max_name_len - (len(short_fingerprint) + 1):
                            display_name = original_name[:max_name_len - (len(short_fingerprint) + 4)] + "..."
                        else:
                            display_name = original_name

                        proxy_dict['name'] = f"{display_name}-{short_fingerprint}"
                        final_filtered_proxies.append(proxy_dict)
                except Exception as exc:
                    print(f"    连通性测试 {server}:{port} 时发生异常: {exc}")

                if processed_count % 50 == 0 or processed_count == total_testable_proxies:
                    print(f"    进度: 已测试 {processed_count}/{total_testable_proxies} 个代理...")
    else:
        print("跳过连通性测试 (已禁用)。所有解析出的唯一代理将被添加。")
        for proxy_dict in proxies_to_test_list:
            original_name = proxy_dict.get('name', f"{proxy_dict.get('type', 'UNKNOWN').upper()}-{proxy_dict.get('server', 'unknown')}")
            short_fingerprint = generate_proxy_fingerprint(proxy_dict)[:6]
            max_name_len = 50

            if len(original_name) > max_name_len - (len(short_fingerprint) + 1):
                display_name = original_name[:max_name_len - (len(short_fingerprint) + 4)] + "..."
            else:
                display_name = original_name

            proxy_dict['name'] = f"{display_name}-{short_fingerprint}"
            final_filtered_proxies.append(proxy_dict)

    print(f"Successfully parsed, deduplicated, tested, and aggregated {len(final_filtered_proxies)} unique and reachable proxy nodes.")
    return final_filtered_proxies, list(successful_urls)

# --- GitHub API Helpers ---
def get_github_file_content(api_url, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    try:
        print(f"DEBUG: 尝试从 GitHub API 获取文件: {api_url}")
        response = requests.get(api_url, headers=headers, timeout=10)
        print(f"DEBUG: GitHub API 响应状态码: {response.status_code}")

        sha = response.headers.get("X-GitHub-Sha")
        if sha is None:
            etag = response.headers.get("ETag")
            if etag:
                sha = etag.strip('"')
                print(f"DEBUG: X-GitHub-Sha 为 None，从 ETag 获取到 SHA: {sha}")
            else:
                print("DEBUG: 既未获取到 X-GitHub-Sha，也未获取到 ETag。")
        else:
            print(f"DEBUG: 从 X-GitHub-Sha 获取到 SHA: {sha}")

        response.raise_for_status()
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

    if not url_list_repo_api:
        print("Error: Environment variable URL_LIST_REPO_API is not set!")
        exit(1)

    try:
        parts = url_list_repo_api.split('/')
        if len(parts) < 8 or parts[2] != 'api.github.com' or parts[3] != 'repos' or parts[6] != 'contents':
            raise ValueError("URL_LIST_REPO_API does not seem to be a valid GitHub Content API URL.")
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except ValueError as ve:
        print(f"Error: {ve}")
        print("Please ensure URL_LIST_REPO_API is correctly set (e.g., https://api.github.com/repos/user/repo/contents/path/to/file.txt).")
        exit(1)
    except IndexError:
        print("Error: URL_LIST_REPO_API format is incorrect. Cannot extract owner, repo, or file path.")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token:
        print("Error: Environment variable BOT is not set!")
        print("Please ensure you've correctly set this variable in GitHub Actions secrets/variables.")
        exit(1)

    print("Fetching URL list and its SHA from GitHub...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        print("Could not get URL list or its SHA, script terminated.")
        exit(1)

    urls = [u for u in url_content.strip().split('\n') if u.strip()]
    print(f"Fetched {len(urls)} non-empty subscription URLs from GitHub.")

    enable_connectivity_test = os.environ.get("ENABLE_CONNECTIVITY_TEST", "true").lower() == "true"

    all_parsed_proxies, successful_urls_list = fetch_and_decode_urls_to_clash_proxies(urls, enable_connectivity_test)

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
            'default-nameserver': ['114.114.114.114', '8.8.8.8'],
            'nameserver': ['https://dns.google/dns-query', 'tls://dns.google'],
            'fallback': ['tls://1.1.1.1', 'tcp://8.8.4.4', 'https://dns.opendns.com/dns-query'],
            'fallback-filter': {'geoip': True, 'geoip-code': 'CN', 'ipcidr': ['240.0.0.0/4']}
        },
        'proxies': all_parsed_proxies,
        'proxy-groups': [
            {
                'name': '🚀 节点选择', 'type': 'select',
                'proxies': ['DIRECT'] + ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else [])
            },
            {
                'name': '📲 国外媒体', 'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT'] + ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else [])
            },
            {
                'name': '🤖 AI/ChatGPT', 'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT'] + ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else [])
            },
            {
                'name': '🌍 其他流量', 'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT'] + ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else [])
            },
            {
                'name': '🐟 漏网之鱼', 'type': 'select',
                'proxies': ['🚀 节点选择', 'DIRECT'] + ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else [])
            },
            {
                'name': '🛑 广告拦截', 'type': 'select',
                'proxies': ['REJECT', 'DIRECT']
            },
            {
                'name': '🔰 Fallback', 'type': 'fallback',
                'proxies': ([p['name'] for p in all_parsed_proxies] if all_parsed_proxies else ['DIRECT']),
                'url': 'http://www.google.com/generate_204', 'interval': 300
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

    if not all_parsed_proxies:
        for group in clash_config['proxy-groups']:
            if group['name'] not in ['🛑 广告拦截', '🔰 Fallback']:
                group['proxies'] = ['DIRECT']
            elif group['name'] == '🔰 Fallback':
                group['proxies'] = ['DIRECT']

    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)
    with open("base64.yaml", "w", encoding="utf-8") as f:
        f.write(final_clash_yaml)
    print("Clash YAML configuration successfully written to base64.yaml")

    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')
    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(final_base64_encoded)
    print("Base64 encoded Clash YAML configuration successfully written to base64.txt")

    new_url_list_content = "\n".join(sorted(list(set(successful_urls_list))))

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
