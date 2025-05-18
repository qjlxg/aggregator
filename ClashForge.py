# -*- coding: utf-8 -*-
import base64
import subprocess
import threading
import time
import urllib.parse
import json
import glob
import re
import yaml
import random
import string
# import httpx # Removed as Clash API is not used
# import asyncio # Removed as async operations for API are not used
from itertools import chain
from typing import Dict, List, Optional
import sys
import requests
import zipfile
import gzip
import shutil
import platform
import os
from datetime import datetime
# from asyncio import Semaphore # Removed
# import ssl # Removed as ssl context modification is not needed without httpx

# ssl._create_default_https_context = ssl._create_unverified_context # Removed

# Constants
# TEST_URL = "http://www.pinterest.com" # Removed as testing is not done
# CLASH_API_PORTS = [9090] # Removed
# CLASH_API_HOST = "127.0.0.1" # Removed
# CLASH_API_SECRET = "" # Removed
# TIMEOUT = 5 # Removed as testing timeout is not needed
# MAX_CONCURRENT_TESTS = 18 # Removed
LIMIT = 286 # This limit seems unused in the provided snippets, keeping it but it might be vestigial.
CONFIG_FILE = 'data/clash_config.yaml'
INPUT = "input"
BAN = ["中国", "China", "CN", "电信", "移动", "联通"] # Node name filtering list
HEADERS = {
    'Accept-Charset': 'utf-8',
    'Accept': 'text/html,application/x-yaml,*/*',
    'User-Agent': 'Clash Verge/1.7.7'
}

# Clash Configuration Template - Simplified, removing API/external controller related fields
CLASH_CONFIG_TEMPLATE = {
    "port": 7890,
    "socks-port": 7891,
    "redir-port": 7892,
    "allow-lan": True,
    "mode": "rule",
    "log-level": "info",
    # "external-controller": "127.0.0.1:9090", # Removed
    "geodata-mode": True,
    "dns": {
        "enable": True,
        "ipv6": False,
        "default-nameserver": ["223.5.5.5", "119.29.29.29"],
        # Other configurations...
    },
    "proxies": [],
    "proxy-groups": [
        # Placeholder groups - assuming these are populated elsewhere or are part of a base config
        # Keeping placeholders as in the original template structure
        {"name": "节点选择", "type": "select", "proxies": []},
        {"name": "自动选择", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": []},
        {"name": "Fallback", "type": "fallback", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": []},
        {"name": "DIRECT", "type": "direct"},
        {"name": "REJECT", "type": "reject"}
    ],
    "rules": [
        # Placeholder rules - assuming these are populated elsewhere or are part of a base config
        # Keeping placeholders as in the original template structure
        "MATCH,节点选择"
    ]
}

# --- Proxy Parsing Functions (Assuming these are complete and correct) ---
# Note: These functions are kept as they are essential for converting links to proxy dictionaries.

def parse_hysteria2_link(link):
    """Parses a Hysteria2 link into a proxy dictionary."""
    # Placeholder for actual parsing logic
    print(f"Parsing Hysteria2 link: {link}")
    try:
        # Example parsing (needs to be replaced with actual logic)
        parsed_url = urllib.parse.urlparse(link)
        server = parsed_url.hostname
        port = parsed_url.port
        params = urllib.parse.parse_qs(parsed_url.query)
        name = urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"
        password = parsed_url.username or params.get('password', [''])[0]
        obfs = params.get('obfs', [''])[0]
        obfs_param = params.get('obfs-param', [''])[0]
        protocol = params.get('protocol', ['udp'])[0]
        up = params.get('up', [''])[0]
        # Corrected syntax error here: 'down': down if down else None
        down = params.get('down', [''])[0]
        alpn = params.get('alpn', [''])[0]
        fast_open = params.get('fast-open', ['false'])[0].lower() == 'true'
        mptcp = params.get('mptcp', ['false'])[0].lower() == 'true'
        # Add other Hysteria2 specific parameters as needed

        return {
            'name': name,
            'type': 'hysteria2',
            'server': server,
            'port': port,
            'password': password,
            'obfs': obfs if obfs else None,
            'obfs-param': obfs_param if obfs_param else None,
            'protocol': protocol,
            'up': up if up else None,
            'down': down if down else None, # Corrected line
            'alpn': [a.strip() for a in alpn.split(',')] if alpn else None,
            'fast-open': fast_open,
            'mptcp': mptcp,
            # Add other Hysteria2 specific fields
        }
    except Exception as e:
        print(f"Error parsing Hysteria2 link {link}: {e}")
        return None

def parse_ss_link(link):
    """Parses a Shadowsocks link into a proxy dictionary."""
    # Placeholder for actual parsing logic
    print(f"Parsing SS link: {link}")
    try:
        # SS links are typically base64 encoded userinfo@server:port#name
        parsed_url = urllib.parse.urlparse(link)
        encoded_userinfo = parsed_url.username
        server = parsed_url.hostname
        port = parsed_url.port
        name = urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"

        if encoded_userinfo:
            # Add padding if necessary
            missing_padding = len(encoded_userinfo) % 4
            if missing_padding:
                encoded_userinfo += '=' * (4 - missing_padding)

            decoded_userinfo = base64.b64decode(encoded_userinfo).decode('utf-8')
            method, password = decoded_userinfo.split(':', 1) # Assuming format is method:password
        else:
            method = None
            password = None

        return {
            'name': name,
            'type': 'ss',
            'server': server,
            'port': port,
            'cipher': method,
            'password': password,
            # Add other SS specific fields
        }
    except Exception as e:
        print(f"Error parsing SS link {link}: {e}")
        return None


def parse_trojan_link(link):
    """Parses a Trojan link into a proxy dictionary."""
    # Placeholder for actual parsing logic
    print(f"Parsing Trojan link: {link}")
    try:
        parsed_url = urllib.parse.urlparse(link)
        password = parsed_url.username
        server = parsed_url.hostname
        port = parsed_url.port
        name = urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"
        params = urllib.parse.parse_qs(parsed_url.query)

        sni = params.get('sni', [None])[0]
        alpn = params.get('alpn', [None])[0]
        allow_insecure = params.get('allowInsecure', ['0'])[0] == '1'
        skip_cert_verify = params.get('skip-cert-verify', ['false'])[0].lower() == 'true'
        # Add other Trojan specific parameters as needed

        return {
            'name': name,
            'type': 'trojan',
            'server': server,
            'port': port,
            'password': password,
            'sni': sni if sni else None,
            'alpn': [a.strip() for a in alpn.split(',')] if alpn else None,
            'skip-cert-verify': skip_cert_verify,
            # 'allowInsecure': allow_insecure # Clash uses skip-cert-verify instead of allowInsecure
            # Add other Trojan specific fields
        }
    except Exception as e:
        print(f"Error parsing Trojan link {link}: {e}")
        return None


def parse_vless_link(link):
    """Parses a VLESS link into a proxy dictionary."""
    # Placeholder for actual parsing logic
    print(f"Parsing VLESS link: {link}")
    try:
        parsed_url = urllib.parse.urlparse(link)
        uuid = parsed_url.username
        server = parsed_url.hostname
        port = parsed_url.port
        name = urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}"
        params = urllib.parse.parse_qs(parsed_url.query)

        # Extract VLESS parameters (flow, encryption, etc.)
        flow = params.get('flow', [None])[0]
        encryption = params.get('encryption', [None])[0] # VLESS usually has 'none' encryption
        # Extract XTLS/TLS/WS/TCP/etc. settings from query parameters
        security = params.get('security', [None])[0]
        sni = params.get('sni', [None])[0]
        alpn = params.get('alpn', [None])[0]
        fp = params.get('fp', [None])[0] # Fingerprint
        pbk = params.get('pbk', [None])[0] # Public Key
        sid = params.get('sid', [None])[0] # Short ID
        type_param = params.get('type', ['tcp'])[0] # Network type (tcp, ws, grpc)

        # WebSocket settings
        ws_path = params.get('path', [None])[0]
        ws_headers_str = params.get('headers', [None])[0]
        ws_headers = {}
        if ws_headers_str:
             # Basic parsing for headers=key:value;key2:value2 (needs robust implementation)
             try:
                 for header_pair in ws_headers_str.split(';'):
                     if ':' in header_pair:
                         key, value = header_pair.split(':', 1)
                         ws_headers[key.strip()] = value.strip()
             except Exception as e:
                 print(f"Warning: Could not parse VLESS WS headers '{ws_headers_str}': {e}")


        # gRPC settings
        grpc_service_name = params.get('serviceName', [None])[0]
        grpc_probe_plain = params.get('probe_plain', ['false'])[0].lower() == 'true'
        grpc_run_plain = params.get('run_plain', ['false'])[0].lower() == 'true'

        # TLS settings
        tls_settings = {}
        if security == 'tls' or security == 'xtls':
             tls_settings = {
                 'serverName': sni if sni else server, # Use sni if available, otherwise server
                 'sni': sni if sni else None,
                 'alpn': [a.strip() for a in alpn.split(',')] if alpn else None,
                 'fingerprint': fp if fp else None,
                 'skip-cert-verify': params.get('allowInsecure', ['0'])[0] == '1' # VLESS often uses allowInsecure
             }
             if security == 'xtls':
                 tls_settings['enable_xtls'] = True
                 tls_settings['flow'] = flow if flow else 'xtls-rprx-vision' # Default XTLS flow

        # Network specific settings
        network_settings = {}
        if type_param == 'ws':
            network_settings = {
                'path': ws_path,
                'headers': ws_headers if ws_headers else None
            }
        elif type_param == 'grpc':
             network_settings = {
                 'serviceName': grpc_service_name,
                 'probe_plain': grpc_probe_plain,
                 'run_plain': grpc_run_plain
             }
        # Add other network types (tcp, http, quic, etc.)

        proxy_dict = {
            'name': name,
            'type': 'vless',
            'server': server,
            'port': port,
            'uuid': uuid,
            'encryption': encryption if encryption else 'none', # Default VLESS encryption
            'network': type_param,
            # Merge TLS/XTLS settings
            **tls_settings,
            # Merge network specific settings
            **network_settings
            # Add other VLESS specific fields
        }

        # Clean up None values
        return {k: v for k, v in proxy_dict.items() if v is not None}

    except Exception as e:
        print(f"Error parsing VLESS link {link}: {e}")
        return None


def parse_vmess_link(link):
    """Parses a VMESS link into a proxy dictionary."""
    # Placeholder for actual parsing logic
    print(f"Parsing VMESS link: {link}")
    try:
        # VMESS links are typically vmess://base64(json)
        if not link.startswith("vmess://"):
            return None

        encoded_json = link[8:]
        # Add padding if necessary
        missing_padding = len(encoded_json) % 4
        if missing_padding:
            encoded_json += '=' * (4 - missing_padding)

        decoded_json_str = base64.b64decode(encoded_json).decode('utf-8')
        config = json.loads(decoded_json_str)

        # Extract fields from the VMESS JSON config
        name = config.get('ps', f"{config.get('add')}:{config.get('port')}") # ps is the name
        server = config.get('add')
        port = config.get('port')
        uuid = config.get('id')
        alterId = config.get('aid', 0)
        cipher = config.get('scy', 'auto') # Security/Cipher
        network = config.get('net', 'tcp')
        type_param = config.get('type', 'none') # Mux type, http, etc.
        host = config.get('host')
        path = config.get('path')
        tls = config.get('tls', '') # "tls" or ""
        sni = config.get('sni')
        alpn = config.get('alpn')
        skip_cert_verify = config.get('allowInsecure', 0) == 1

        proxy_dict = {
            'name': name,
            'type': 'vmess',
            'server': server,
            'port': port,
            'uuid': uuid,
            'alterId': alterId,
            'cipher': cipher,
            'network': network,
            'tls': tls.lower() == 'tls', # Boolean
            'skip-cert-verify': skip_cert_verify,
            # Network specific settings
            'ws-path': path if network == 'ws' else None,
            'ws-headers': {'Host': host} if network == 'ws' and host else None,
            'grpc-serviceName': path if network == 'grpc' else None, # path is serviceName for gRPC
            # TLS specific settings
            'servername': sni if sni else (host if network == 'ws' else None), # Use host as servername for WS if sni is missing
            'alpn': [a.strip() for a in alpn.split(',')] if alpn else None,
            'host': host if network != 'ws' else None # Host is used differently for WS
        }

        # Clean up None values
        return {k: v for k, v in proxy_dict.items() if v is not None}

    except Exception as e:
        print(f"Error parsing VMESS link {link}: {e}")
        return None

# Assuming parse_ss_sub, parse_md_link, js_render, match_nodes, process_url are also defined
# and handle other link types or crawling logic.
# Since the request is to remove node checking, these functions are assumed to work
# to produce raw links or proxy dictionaries that the main logic will then process.

def parse_ss_sub(link):
    """Parses a Shadowsocks subscription link (base64 encoded SS links)."""
    print(f"Parsing SS sub link: {link}")
    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text.strip()

        # Add padding if necessary
        missing_padding = len(content) % 4
        if missing_padding:
            content += '=' * (4 - missing_padding)

        decoded_content = base64.b64decode(content).decode('utf-8')
        # The decoded content is expected to be multiple SS links, one per line
        ss_links = [line.strip() for line in decoded_content.splitlines() if line.strip()]
        return [parse_ss_link(ss_link) for ss_link in ss_links if ss_link.startswith("ss://")]
    except Exception as e:
        print(f"Error processing SS subscription link {link}: {e}")
        return []

def parse_md_link(link):
    """Parses links from a Markdown file URL."""
    print(f"Parsing Markdown link: {link}")
    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text
        # Simple regex to find potential proxy links in markdown code blocks or inline code
        # This is a basic example and might need refinement based on actual markdown format
        pattern = r"```.*?([\w]+:\/\/[^\s`]+)```|`([\w]+:\/\/[^\s`]+)`"
        found_links = re.findall(pattern, content, re.DOTALL)
        # Flatten the list of tuples and filter out empty strings
        links = [item for sublist in found_links for item in sublist if item]
        return links
    except Exception as e:
        print(f"Error processing Markdown link {link}: {e}")
        return []

# Assuming js_render and match_nodes are used for more complex web scraping
# Keeping placeholders as they might be called by process_url
def js_render(url):
    """Renders a JavaScript-heavy page (Placeholder)."""
    print(f"Attempting JS render for {url}")
    # This would require a headless browser like Playwright or Puppeteer
    # Returning empty for now as implementation is complex and external
    return None # Or a mock response object if needed by match_nodes

def match_nodes(text):
    """Matches proxy links in arbitrary text (Placeholder)."""
    print("Matching nodes in text...")
    # This would contain regex or other logic to find proxy links
    # Returning empty list for now
    return []

def process_url(url):
    """Processes a general URL to find proxy links."""
    print(f"Processing general URL: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text

        # Attempt to find links in the text content
        # This regex looks for common proxy scheme prefixes
        pattern = r"(ss|vmess|vless|trojan|hysteria2):\/\/[^\s]+"
        found_links = re.findall(pattern, content)

        if found_links:
            return found_links
        else:
            # If no direct links, try JS rendering if applicable (placeholder)
            # rendered_content = js_render(url)
            # if rendered_content:
            #     return match_nodes(rendered_content.html.full_text)
            pass # Skip JS rendering for now

        return [] # Return empty list if no links found
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return []


def parse_proxy_link(link):
    """Parses a single proxy link based on its scheme."""
    if link.startswith("ss://"):
        return parse_ss_link(link)
    elif link.startswith("vmess://"):
        return parse_vmess_link(link)
    elif link.startswith("vless://"):
        return parse_vless_link(link)
    elif link.startswith("trojan://"):
        return parse_trojan_link(link)
    elif link.startswith("hysteria2://"):
        return parse_hysteria2_link(link)
    # Add other schemes if needed
    else:
        print(f"Unsupported link scheme: {link}")
        return None

def deduplicate_proxies(proxies_list):
    """Deduplicates a list of proxy dictionaries based on a unique key."""
    seen_keys = set()
    unique_proxies = []
    for proxy in proxies_list:
        if not isinstance(proxy, dict):
            continue # Skip invalid entries

        # Create a unique key based on relevant fields
        # This key should be robust enough to identify identical proxies
        # Consider server, port, type, and a primary identifier (uuid, password, etc.)
        proxy_type = proxy.get('type')
        server = proxy.get('server')
        port = proxy.get('port')
        identifier = None

        if proxy_type == 'vmess':
            identifier = proxy.get('uuid')
        elif proxy_type == 'vless':
            identifier = proxy.get('uuid')
        elif proxy_type == 'trojan':
            identifier = proxy.get('password')
        elif proxy_type == 'ss':
            identifier = f"{proxy.get('cipher')}:{proxy.get('password')}"
        elif proxy_type == 'hysteria2':
             identifier = proxy.get('password') # Or a combination of params

        # Create the key - use a tuple for hashability
        proxy_key = (proxy_type, server, port, identifier)

        if None not in proxy_key and proxy_key not in seen_keys:
            unique_proxies.append(proxy)
            seen_keys.add(proxy_key)
        elif None in proxy_key:
             print(f"Skipping proxy with incomplete info for deduplication: {proxy}")

    print(f"Deduplicated {len(proxies_list)} proxies to {len(unique_proxies)}")
    return unique_proxies

def add_random_suffix(name, existing_names):
    """Adds a random suffix to a name to avoid conflicts."""
    original_name = name
    while name in existing_names:
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        name = f"{original_name}_{suffix}"
    existing_names.add(name)
    return name

def read_txt_files(folder_path):
    """Reads all lines from .txt files in a folder."""
    all_lines = []
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    for file_path in txt_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                all_lines.extend(line.strip() for line in file.readlines() if line.strip())
        except Exception as e:
            print(f"Error reading txt file {file_path}: {e}")
    return all_lines

def read_yaml_files(folder_path):
    """Reads proxy lists from .yaml or .yml files in a folder."""
    load_nodes = []
    yaml_files = glob.glob(os.path.join(folder_path, '*.yaml')) + glob.glob(os.path.join(folder_path, '*.yml'))
    for file_path in yaml_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                if isinstance(config, dict) and "proxies" in config and isinstance(config["proxies"], list):
                    load_nodes.extend(config["proxies"])
                else:
                    print(f"Warning: {file_path} does not contain a valid 'proxies' list.")
        except Exception as e:
            print(f"Error reading yaml file {file_path}: {e}")
    return load_nodes

def filter_by_types_alt(allowed_types, nodes):
    """Filters a list of nodes by their type."""
    if not allowed_types:
        return nodes # Return all nodes if no types specified
    return [x for x in nodes if isinstance(x, dict) and x.get('type') in allowed_types]

def merge_lists(*lists):
    """Merges multiple lists, filtering out empty strings."""
    return [item for item in chain.from_iterable(lists) if item != '']

# Removed handle_links as its logic is integrated into generate_clash_config

def generate_clash_config(links, load_nodes, allowed_types):
    """
    Generates Clash configuration from links and loaded nodes.
    Does NOT perform node availability checks.
    """
    print("Generating Clash configuration...")
    now = datetime.now()
    all_collected_proxies = []
    existing_names = set() # To track names for conflict resolution

    # Function to resolve name conflicts and add to all_collected_proxies
    def add_proxy_with_name_check(node):
        if not isinstance(node, dict):
            print(f"Skipping invalid node entry: {node}")
            return

        # Ensure node has a name, generate one if missing
        if not node.get('name'):
             node['name'] = f"{node.get('type', 'unknown')}-{node.get('server', 'unknown')}:{node.get('port', 'unknown')}"
             print(f"Warning: Node missing name, generated: {node['name']}")

        original_name = str(node["name"])
        # Filter out nodes whose names contain banned keywords
        if not_contains(original_name):
            # Resolve name conflicts by adding a suffix
            node["name"] = add_random_suffix(original_name, existing_names)
            all_collected_proxies.append(node)
        else:
            print(f"Skipping node with banned keyword in name: {original_name}")


    # Process nodes loaded from YAML files
    for node in load_nodes:
        add_proxy_with_name_check(node)

    # Process links from TXT files and initial links list
    for link in links:
        if link.startswith(("ss://", "vmess://", "vless://", "trojan://", "hysteria2://")):
            node = parse_proxy_link(link)
            if node:
                add_proxy_with_name_check(node)
        elif link.startswith(("http://", "https://")):
             # Attempt to process general URLs that might contain multiple links
             found_links = process_url(link)
             for found_link in found_links:
                 node = parse_proxy_link(found_link)
                 if node:
                      add_proxy_with_name_check(node)
        elif link.strip(): # Handle non-empty lines that are not valid links
             print(f"跳过无法解析的链接或行: {link}")


    # Deduplicate the collected proxies
    final_proxies = deduplicate_proxies(all_collected_proxies)

    # Filter by allowed types after deduplication
    if allowed_types:
        final_proxies = filter_by_types_alt(allowed_types, final_proxies)
        print(f"Filtered to {len(final_proxies)} nodes by types: {allowed_types}")

    # Populate the Clash config template
    config = CLASH_CONFIG_TEMPLATE.copy()
    config["proxies"] = final_proxies

    # Populate proxy groups with the names of the final proxies
    # Assuming the placeholder groups in CLASH_CONFIG_TEMPLATE are the intended ones
    proxy_names = [p['name'] for p in final_proxies]

    # Find the index of the "节点选择" group and populate its proxies
    select_group_index = -1
    auto_select_group_index = -1
    fallback_group_index = -1

    for i, group in enumerate(config["proxy-groups"]):
        if group.get("name") == "节点选择":
            select_group_index = i
        elif group.get("name") == "自动选择":
             auto_select_group_index = i
        elif group.get("name") == "Fallback":
             fallback_group_index = i


    if select_group_index != -1:
        # Add DIRECT and REJECT to the select group
        config["proxy-groups"][select_group_index]["proxies"] = ["自动选择", "Fallback", "DIRECT", "REJECT"] + proxy_names
    else:
        print("Warning: '节点选择' proxy group not found in template.")

    if auto_select_group_index != -1:
         config["proxy-groups"][auto_select_group_index]["proxies"] = proxy_names
    else:
        print("Warning: '自动选择' proxy group not found in template.")

    if fallback_group_index != -1:
         config["proxy-groups"][fallback_group_index]["proxies"] = proxy_names
    else:
        print("Warning: 'Fallback' proxy group not found in template.")


    # Ensure the data directory exists before saving
    data_dir = os.path.dirname(CONFIG_FILE)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # Save the configuration to YAML and JSON files
    if config["proxies"]:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False) # sort_keys=False to maintain order
            print(f"已生成Clash配置文件: {CONFIG_FILE}")
        except Exception as e:
            print(f"Error saving YAML config {CONFIG_FILE}: {e}")

        try:
            # Use a different filename for JSON if needed, or just add .json extension
            json_config_file = f'{CONFIG_FILE}.json'
            with open(json_config_file, "w", encoding="utf-8") as f:
                # Use indent for readability in JSON
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"已生成Clash配置文件: {json_config_file}")
        except Exception as e:
            print(f"Error saving JSON config {json_config_file}: {e}")

    else:
        print('没有节点数据更新，未生成配置文件。')


def not_contains(s):
    """Checks if a string contains any banned keywords."""
    if not isinstance(s, str):
        return True # Treat non-string names as containing banned keywords
    return not any(k in s for k in BAN)

# Removed all functions related to starting Clash subprocess and API interaction

def work_no_check(links, allowed_types=[]):
    """
    Main function to handle the work without node availability checks.
    Collects nodes, deduplicates, filters, and generates config files.
    """
    try:
        # Read existing nodes from YAML files in the input folder
        load_nodes = read_yaml_files(folder_path=INPUT)
        print(f"从 {INPUT} 目录加载到 {len(load_nodes)} 个现有节点。")

        # Read links from TXT files in the input folder
        txt_links = read_txt_files(folder_path=INPUT)
        print(f"从 {INPUT} 目录加载到 {len(txt_links)} 条链接。")

        # Merge initial links with links from TXT files
        all_links = merge_lists(links, txt_links)
        print(f"总共收集到 {len(all_links)} 条待处理链接。")

        # Generate Clash configuration directly from collected links and nodes
        if all_links or load_nodes:
            generate_clash_config(all_links, load_nodes, allowed_types)
        else:
            print("没有链接或现有节点可供处理，退出。")

    except KeyboardInterrupt:
        print("\n用户中断执行")
        sys.exit(0)
    except Exception as e:
        print(f"程序执行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    # Define initial links (can be subscription URLs, raw proxy links, or file URLs)
    links = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.yaml", # Example YAML URL
        "https://raw.githubusercontent.com/mermeroo/V2RAY-CLASH-BASE64-Subscription.Links/main/SUB%20LINKS", # Example Base64 URL
        # Add other URLs here
        # Example raw link: "ss://YWVzLTI1Ni1nY206VGVzdDEyM0AxLjIuMy40OjEyMzQ1#TestNode"
    ]

    # Define allowed proxy types for filtering (optional)
    allowed_types_filter = ["ss", "hysteria2", "hy2", "vless", "vmess", "trojan"] # Example types

    # Run the main work function without node checking
    work_no_check(links, allowed_types=allowed_types_filter)
