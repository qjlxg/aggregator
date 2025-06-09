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
                            proxies_from_b64_in_utf8 = _ вік

