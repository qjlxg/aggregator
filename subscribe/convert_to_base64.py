import requests
import base64
import os
import json
import re
import yaml # pip install PyYAML
from urllib.parse import urlparse, parse_qs, unquote
import hashlib # 用于生成哈希指纹

# --- Proxy Parsing Functions (Modified to return more detailed info for fingerprinting) ---

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
    # 对于插件信息，如果它是一个复杂的字典，可能需要将其转换为可哈希的字符串
    # 为了简化和确保单行，我们之前已经将其尝试扁平化为字符串
    parts.append(str(proxy_data.get('plugin-info', ''))) 
    parts.append(str(proxy_data.get('alpn', ''))) # for hysteria2

    # 使用json.dumps来确保字典和列表的顺序一致性，使其可哈希
    # 但由于我们的目标是单行字典，通常不会有嵌套的dict/list作为值
    # 这里直接拼接字符串更高效且符合预期
    
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
            'name': name, # 临时名称，后面会标准化
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
                # 尽量将 headers 转换为字符串，以保持代理字典扁平
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
        
        if '#' in encoded_part:
            encoded_part, fragment = encoded_part.split('#', 1)
            name = unquote(fragment)
        else:
            name = "Shadowsocks"

        plugin_info_str = ""
        if '/?plugin=' in encoded_part:
            encoded_part, plugin_info_str = encoded_part.split('/?plugin=', 1)
        
        decoded_str = base64.urlsafe_b64decode(encoded_part + '==').decode('utf-8')
        parts = decoded_str.split('@')
        method_password = parts[0].split(':', 1)
        method = method_password[0]
        password = method_password[1]
        
        server_port = parts[1].split(':')
        server = server_port[0]
        port = int(server_port[1])
        
        proxy = {
            'name': name,
            'type': 'ss',
            'server': server,
            'port': port,
            'cipher': method,
            'password': password,
        }

        if plugin_info_str:
            # 存储为字符串，以避免复杂嵌套导致多行
            proxy['plugin-info'] = plugin_info_str 
        
        return proxy
    except Exception as e:
        print(f"解析 Shadowsocks 链接失败: {ss_url[:50]}...，原因: {e}")
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
            # 将 alpn 列表转换为逗号分隔的字符串
            proxy['alpn'] = ','.join(params['alpn']) 

        return proxy
    except Exception as e:
        print(f"解析 Hysteria2 链接失败: {hy2_url[:50]}...，原因: {e}")
        return None

# --- Fetch and Decode URLs (Modified for deduplication and naming) ---
def fetch_and_decode_urls_to_clash_proxies(urls):
    # 使用字典来存储唯一的代理，key 是指纹，value 是 Clash 代理配置
    unique_proxies = {} 
    successful_urls = []

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
                        
                        if not current_proxies:
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

            except UnicodeDecodeError:
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
                    content.decode('latin-1', errors='ignore')
                    print(f"Warning: Could not decode content from {url} to UTF-8, GBK, or Base64. Using latin-1 and ignoring errors.")

            # --- Deduplication and Name Standardization Logic ---
            for proxy_dict in current_proxies:
                if proxy_dict: # 确保代理字典不是None
                    fingerprint = generate_proxy_fingerprint(proxy_dict)
                    if fingerprint not in unique_proxies:
                        # 生成标准化名称：协议_服务器_端口_指纹_序号 (为防止重复，可以加个计数器)
                        # 这里我们简化为 协议-服务器-指纹后四位
                        base_name = f"{proxy_dict.get('type', 'unknown').upper()}-{proxy_dict.get('server', 'unknown')}"
                        # 防止名称过长，截断指纹
                        proxy_dict['name'] = f"{base_name}-{fingerprint[:8]}" 
                        unique_proxies[fingerprint] = proxy_dict
                        print(f"    添加新代理: {proxy_dict['name']}")
                    else:
                        print(f"    跳过重复代理 (指纹: {fingerprint})")
            
            if current_proxies: # 如果这个URL成功解析出代理（即使是重复的）
                successful_urls.append(url)

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch data from URL: {url}, reason: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing URL {url}: {e}")

    final_proxies_list = list(unique_proxies.values())
    print(f"Successfully parsed, deduplicated, and aggregated {len(final_proxies_list)} unique proxy nodes.")
    return final_proxies_list, successful_urls

# --- GitHub API Helpers (不变) ---
def get_github_file_content(api_url, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        sha = response.headers.get("X-GitHub-Sha")
        return response.text, sha
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file from GitHub: {e}")
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

# --- Main Function (不变) ---
def main():
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    
    try:
        parts = url_list_repo_api.split('/')
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except IndexError:
        print("Error: URL_LIST_REPO_API format is incorrect. Ensure it's a GitHub API file content link.")
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

    # 重点：现在 fetch_and_decode_urls_to_clash_proxies 返回的是经过去重和命名标准化的代理字典列表
    all_parsed_proxies, successful_urls = fetch_and_decode_urls_to_clash_proxies(urls)

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
            ]
            }
        },
        'proxies': all_parsed_proxies, # 填入所有解析出的代理

        # 示例代理组 (可根据需要自定义)
        'proxy-groups': [
            {
                'name': '🚀 节点选择',
                'type': 'select',
                'proxies': ['DIRECT'] + [p['name'] for p in all_parsed_proxies] # 添加DIRECT选项
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
        # 示例规则 (可根据需要自定义)
        'rules': [
            'DOMAIN-KEYWORD,openai,🤖 AI/ChatGPT',
            'DOMAIN-KEYWORD,google,📲 国外媒体',
            'DOMAIN-KEYWORD,youtube,📲 国外媒体',
            'DOMAIN-KEYWORD,netflix,📲 国外媒体',
            'DOMAIN-KEYWORD,github,🌍 其他流量', # GitHub也通过代理，防止被墙
            'DOMAIN-SUFFIX,cn,DIRECT',
            'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve',
            'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
            'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,127.0.0.1/8,DIRECT,no-resolve',
            'GEOIP,CN,DIRECT,no-resolve',
            'MATCH,🐟 漏网之鱼'
        ]
    }
    
    # 关键行: 使用 default_flow_style=False 鼓励单行输出字典
    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    # 编码为Base64
    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')

    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(final_base64_encoded)
    print("Base64 编码的 Clash YAML 配置已成功写入 base64.txt")

    # ... (更新 url.txt 的逻辑保持不变)
    new_url_list_content = "\n".join(sorted(list(set(successful_urls))))
    
    if new_url_list_content.strip() != url_content.strip():
        print("正在更新 GitHub 上的 url.txt 文件...")
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
            print("url.txt 文件已成功更新。")
        else:
            print("更新 url.txt 文件失败。")
    else:
        print("url.txt 文件内容未改变，无需更新。")

if __name__ == "__main__":
    main()
