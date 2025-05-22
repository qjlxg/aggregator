import requests
import base64
import yaml
import re
import os
import hashlib
import concurrent.futures
import time
import socket
import struct
import json
import ipaddress # For IP address validation
import sys

# --- Configuration (from environment variables) ---
# Maximum workers for concurrent connectivity tests (default: 30)
MAX_WORKERS_CONNECTIVITY_TEST = int(os.getenv('MAX_WORKERS_CONNECTIVITY_TEST', '30'))

# TCP connectivity test timeout in seconds (default: 1)
TCP_TIMEOUT = float(os.getenv('TCP_TIMEOUT', '1'))

# TCP connectivity test retries (default: 1)
TCP_RETRIES = int(os.getenv('TCP_RETRIES', '1'))

# TCP connectivity test delay between retries in seconds (default: 0.5)
TCP_DELAY = float(os.getenv('TCP_DELAY', '0.5'))

# URL list repository API endpoint (e.g., from GitHub API for a specific file)
URL_LIST_REPO_API = os.getenv('URL_LIST_REPO_API')

# Clash template path
CLASH_TEMPLATE_PATH = os.getenv('CLASH_TEMPLATE_PATH', 'clash_template.yml')

# Enable/Disable connectivity test (default: "true")
ENABLE_CONNECTIVITY_TEST = os.getenv('ENABLE_CONNECTIVITY_TEST', 'true').lower() == 'true'

# Exclude nodes by server keyword (comma-separated, case-insensitive)
EXCLUDE_NODES_BY_SERVER_RAW = os.getenv('EXCLUDE_NODES_BY_SERVER', '')
EXCLUDE_NODES_BY_SERVER = [k.strip().lower() for k in EXCLUDE_NODES_BY_SERVER_RAW.split(',') if k.strip()]

# Exclude keywords from subscription URLs (e.g., 'rules', 'filter')
EXCLUDE_KEYWORDS_RAW = os.getenv('EXCLUDE_KEYWORDS', 'rules,filter')
EXCLUDE_KEYWORDS = [k.strip().lower() for k in EXCLUDE_KEYWORDS_RAW.split(',') if k.strip()]

# Exclude China Mainland IP addresses (default: "true")
EXCLUDE_CHINA_NODES = os.getenv('EXCLUDE_CHINA_NODES', 'true').lower() == 'true'

# Path to GeoIP database (e.g., Country.mmdb)
GEOIP_DB_PATH = os.getenv('GEOIP_DB_PATH', 'clash/Country.mmdb')

# --- Global Variables ---
_country_db = None

# --- Helper Functions ---

def load_geoip_db():
    global _country_db
    if _country_db is None and GEOIP_DB_PATH and os.path.exists(GEOIP_DB_PATH):
        try:
            import maxminddb
            _country_db = maxminddb.open_database(GEOIP_DB_PATH)
            print(f"GeoIP database loaded from: {GEOIP_DB_PATH}")
        except ImportError:
            print("Warning: maxminddb not installed. GeoIP lookup will be skipped.")
            _country_db = None
        except FileNotFoundError:
            print(f"Warning: GeoIP database not found at {GEOIP_DB_PATH}. GeoIP lookup will be skipped.")
            _country_db = None
        except Exception as e:
            print(f"Warning: Error loading GeoIP database: {e}. GeoIP lookup will be skipped.")
            _country_db = None
    elif _country_db is None and not GEOIP_DB_PATH:
        print("Info: GEOIP_DB_PATH is not set. GeoIP lookup will be skipped.")
    return _country_db

def is_china_ip(ip_address):
    """Checks if an IP address belongs to China using GeoIP database."""
    if not EXCLUDE_CHINA_NODES:
        return False

    global _country_db
    if _country_db is None:
        _country_db = load_geoip_db() # Attempt to load if not already loaded

    if _country_db:
        try:
            # Ensure the IP is a valid IP address string before lookup
            ip_obj = ipaddress.ip_address(ip_address)
            record = _country_db.get(str(ip_obj))
            if record and 'country' in record and record['country'].get('iso_code') == 'CN':
                return True
        except ValueError:
            # Not a valid IP address, treat as non-China to be safe, or log it
            return False
        except Exception as e:
            print(f"Error during GeoIP lookup for {ip_address}: {e}")
            return False
    return False

# --- MODIFIED generate_proxy_fingerprint FUNCTION ---
def generate_proxy_fingerprint(proxy_dict):
    """Generates a unique fingerprint for a proxy based on its *core* key attributes."""
    core_attributes = {}
    
    # Always include type, server, and port
    core_attributes['type'] = proxy_dict.get('type', 'unknown').lower()
    core_attributes['server'] = proxy_dict.get('server', '').lower()
    core_attributes['port'] = proxy_dict.get('port')

    # Add protocol-specific core identity attributes
    if core_attributes['type'] == 'vmess':
        core_attributes['uuid'] = proxy_dict.get('uuid', '')
        # For Vmess, alterId is often a minor config, not core identity,
        # but sometimes a provider might offer different alterIds for the *same* physical node.
        # If you want to deduplicate Vmess nodes with different alterIds, exclude it from fingerprint.
        # If you want to keep Vmess nodes with different alterIds as distinct, include it.
        # Let's keep it out for now, to maximize deduplication.
        # core_attributes['alterId'] = proxy_dict.get('alterId')
    elif core_attributes['type'] == 'trojan':
        core_attributes['password'] = proxy_dict.get('password', '')
    elif core_attributes['type'] == 'ss': # Shadowsocks
        core_attributes['cipher'] = proxy_dict.get('cipher', '')
        core_attributes['password'] = proxy_dict.get('password', '')
    elif core_attributes['type'] == 'hysteria2':
        core_attributes['password'] = proxy_dict.get('password', '')
        # Obfs and Obfs-password might be seen as core for Hysteria2 obfuscation.
        # If you consider different obfs methods/passwords on the same server/port
        # as different *logical* nodes, include them.
        # For simple physical de-duplication, keep them out. Let's include for H2 as they are critical.
        core_attributes['obfs'] = proxy_dict.get('obfs', '')
        core_attributes['obfs-password'] = proxy_dict.get('obfs-password', '')

    # Ensure a consistent order of keys for hashing
    proxy_str = json.dumps(core_attributes, sort_keys=True)
    return hashlib.sha1(proxy_str.encode('utf-8')).hexdigest()

# --- Connectivity Test Function (remains the same) ---
def test_tcp_connectivity(server, port):
    """Tests TCP connectivity to a given server and port with retries."""
    if not server or not isinstance(port, int):
        return False
    
    # Validate server as IP or domain
    try:
        ipaddress.ip_address(server) # Check if it's a valid IP
        is_ip = True
    except ValueError:
        is_ip = False # It's likely a domain name

    for i in range(TCP_RETRIES + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TCP_TIMEOUT)
        try:
            if not is_ip:
                # Resolve domain to IP for more reliable connection testing
                # DNS resolution can fail here, too.
                ip_address = socket.gethostbyname(server)
            else:
                ip_address = server

            # Exclude China IP addresses if configured
            if EXCLUDE_CHINA_NODES and is_china_ip(ip_address):
                # print(f"    跳过中国大陆IP节点 {server}:{port} (GeoIP).")
                return False # Explicitly return False for excluded China IPs

            s.connect((ip_address, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError, socket.gaierror) as e:
            # socket.gaierror for DNS resolution errors
            # print(f"    TCP 连接失败: {server}:{port} (尝试 {i+1}/{TCP_RETRIES+1}) - {e}")
            if i < TCP_RETRIES:
                time.sleep(TCP_DELAY)
            continue
        finally:
            s.close()
    return False

# --- Proxy Parsing Helper Functions (remain the same) ---

# --- Universal Clash Proxy Parser ---
def _parse_clash_proxy_common(link_type, link_data):
    """Parses common attributes for Clash proxy types."""
    proxy_dict = {'type': link_type}
    try:
        parts = link_data.split('#')
        params_str = parts[0]
        if len(parts) > 1:
            try:
                # Name is URL-decoded
                proxy_dict['name'] = requests.utils.unquote(parts[1])
            except Exception:
                proxy_dict['name'] = parts[1] # Fallback if unquote fails
        
        # Parse params string for server and port first if possible
        # This part depends on the specific protocol's parameter format
        # Example: ss://method:password@server:port
        # Generic approach for common server:port pattern (needs refinement per protocol)
        if '@' in params_str:
            auth_server_part = params_str.split('@', 1)[1]
        else:
            auth_server_part = params_str # No auth part, direct server string
        
        if ':' in auth_server_part:
            server_port_parts = auth_server_part.rsplit(':', 1)
            proxy_dict['server'] = server_port_parts[0].strip()
            try:
                proxy_dict['port'] = int(server_port_parts[1].strip())
            except ValueError:
                pass # Port not an integer, handled below

    except Exception as e:
        print(f"Error parsing common proxy attributes for {link_type} link: {e}")
    return proxy_dict

# Vmess
def parse_vmess(link):
    """Parses a Vmess link."""
    # Vmess links are base64 encoded JSON
    if not link.startswith("vmess://"):
        return None
    try:
        encoded_data = link[len("vmess://"):].strip()
        # Add padding if necessary
        missing_padding = len(encoded_data) % 4
        if missing_padding:
            encoded_data += '=' * (4 - missing_padding)

        decoded_data = base64.b64decode(encoded_data).decode('utf-8')
        vmess_config = json.loads(decoded_data)
        
        # Map Vmess config to Clash proxy format
        proxy = {
            'name': vmess_config.get('ps', vmess_config.get('id', 'vmess_node')),
            'type': 'vmess',
            'server': vmess_config.get('add'),
            'port': int(vmess_config.get('port')),
            'uuid': vmess_config.get('id'),
            'alterId': int(vmess_config.get('aid', 0)),
            'cipher': vmess_config.get('scy', 'auto'),
            'udp': True,
            'network': vmess_config.get('net', 'tcp'),
        }
        
        # Add TLS settings if present
        if vmess_config.get('tls') == 'tls':
            proxy['tls'] = True
            proxy['skip-cert-verify'] = vmess_config.get('v', '') != '2' and vmess_config.get('sni') == '' # if v=2 or sni exists, skip is false
            proxy['servername'] = vmess_config.get('host', '') if vmess_config.get('host') else vmess_config.get('sni', '')
            if proxy['servername'] == '': # If both host and sni are empty, set to server
                proxy['servername'] = proxy['server']

        # Add network specific settings
        if proxy['network'] == 'ws':
            proxy['ws-opts'] = {
                'path': vmess_config.get('path', '/'),
                'headers': {'Host': vmess_config.get('host', '')}
            }
        elif proxy['network'] == 'grpc':
            proxy['grpc-opts'] = {
                'serviceName': vmess_config.get('path', ''),
                'grpcMode': 'gun' if vmess_config.get('host') == 'gun' else 'direct' # simplified, check actual spec
            }
        
        # Clean up name if it's just the uuid
        if proxy['name'] == proxy['uuid']:
            proxy['name'] = f"vmess-{proxy['server']}:{proxy['port']}"

        # Ensure server and port are valid
        if not proxy['server'] or not proxy['port']:
            return None

        return proxy
    except Exception as e:
        # print(f"Failed to parse Vmess link: {link} - Error: {e}")
        return None

# Trojan
def parse_trojan(link):
    """Parses a Trojan link."""
    if not link.startswith("trojan://"):
        return None
    try:
        # trojan://password@server:port#name
        # trojan://password@server:port?param=value#name
        parts_hash = link[len("trojan://"):].split('#', 1)
        uri = parts_hash[0]
        name = requests.utils.unquote(parts_hash[1]) if len(parts_hash) > 1 else 'trojan_node'

        parts_at = uri.split('@', 1)
        password = parts_at[0]
        server_info = parts_at[1] if len(parts_at) > 1 else ''

        parts_query = server_info.split('?', 1)
        server_port_str = parts_query[0]
        query_params = {}
        if len(parts_query) > 1:
            for param in parts_query[1].split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value

        server, port = None, None
        if ':' in server_port_str:
            server_parts = server_port_str.rsplit(':', 1)
            server = server_parts[0]
            port = int(server_parts[1])
        
        if not server or not port:
            return None

        proxy = {
            'name': name,
            'type': 'trojan',
            'server': server,
            'port': port,
            'password': password,
            'udp': True,
            'tls': True,
            'skip-cert-verify': query_params.get('allowInsecure', '0') == '1',
            'servername': query_params.get('peer', server),
            'network': query_params.get('type', 'tcp')
        }

        if proxy['network'] == 'ws':
            proxy['ws-opts'] = {
                'path': query_params.get('path', '/'),
                'headers': {'Host': query_params.get('host', server)}
            }
        elif proxy['network'] == 'grpc':
            proxy['grpc-opts'] = {
                'serviceName': query_params.get('serviceName', ''),
                'grpcMode': query_params.get('mode', 'gun') # direct or gun
            }
        
        return proxy
    except Exception as e:
        # print(f"Failed to parse Trojan link: {link} - Error: {e}")
        return None

# Shadowsocks
def parse_shadowsocks(link):
    """Parses a Shadowsocks link."""
    if not link.startswith("ss://"):
        return None
    try:
        # ss://base64encoded_method_password@server:port#name
        # ss://base64encoded_method_password@server:port?plugin=...#name
        link_data = link[len("ss://"):].strip()
        
        parts_hash = link_data.split('#', 1)
        encoded_part = parts_hash[0]
        name = requests.utils.unquote(parts_hash[1]) if len(parts_hash) > 1 else 'shadowsocks_node'

        # Separate the @ from the server:port part for plugins
        at_parts = encoded_part.split('@', 1)
        if len(at_parts) != 2:
            return None # Invalid SS format

        # Plugin info
        plugin_info_str = ''
        if '?' in at_parts[1]:
            server_port_part_temp = at_parts[1].split('?', 1)
            server_port_str = server_port_part_temp[0]
            plugin_info_str = server_port_part_temp[1]
        else:
            server_port_str = at_parts[1]

        # Decode method:password
        decoded_method_password_b64 = at_parts[0]
        missing_padding = len(decoded_method_password_b64) % 4
        if missing_padding:
            decoded_method_password_b64 += '=' * (4 - missing_padding)
        decoded_method_password = base64.b64decode(decoded_method_password_b64).decode('utf-8')
        
        method_password_parts = decoded_method_password.split(':', 1)
        if len(method_password_parts) != 2:
            return None # Invalid method:password format

        method = method_password_parts[0]
        password = method_password_parts[1]
        
        server_parts = server_port_str.rsplit(':', 1)
        server = server_parts[0]
        port = int(server_parts[1])

        proxy = {
            'name': name,
            'type': 'ss',
            'server': server,
            'port': port,
            'cipher': method,
            'password': password,
            'udp': True
        }

        if plugin_info_str:
            plugin_params = {}
            for param in plugin_info_str.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    plugin_params[key] = value

            if 'plugin' in plugin_params:
                plugin_name = plugin_params['plugin']
                plugin_opts_raw = plugin_params.get('plugin-opts', '')
                
                proxy['plugin'] = plugin_name
                proxy['plugin-opts'] = {}
                if plugin_opts_raw:
                    # Parse plugin-opts string (e.g., "tls;host=example.com")
                    opts = plugin_opts_raw.split(';')
                    for opt in opts:
                        if '=' in opt:
                            k, v = opt.split('=', 1)
                            proxy['plugin-opts'][k] = v
                        else:
                            # For boolean flags like 'tls'
                            if opt:
                                proxy['plugin-opts'][opt] = True # or similar boolean value
                
                # Special handling for obfs/v2ray-plugin (Clash requires tls for obfs)
                if plugin_name in ['obfs-local', 'v2ray-plugin']:
                    if proxy['plugin-opts'].get('tls'):
                        proxy['tls'] = True
                        if 'host' in proxy['plugin-opts']:
                            proxy['servername'] = proxy['plugin-opts']['host']
                            proxy['skip-cert-verify'] = proxy['plugin-opts'].get('tls-no-verify', '0') == '1'
                    else:
                        proxy['tls'] = False # Ensure not set if not using TLS

        return proxy
    except Exception as e:
        # print(f"Failed to parse Shadowsocks link: {link} - Error: {e}")
        return None

# Hysteria2
def parse_hysteria2(link):
    """Parses a Hysteria2 link."""
    if not link.startswith("hysteria2://"):
        return None
    try:
        # hysteria2://password@server:port?params#name
        parts_hash = link[len("hysteria2://"):].split('#', 1)
        uri = parts_hash[0]
        name = requests.utils.unquote(parts_hash[1]) if len(parts_hash) > 1 else 'hysteria2_node'

        parts_at = uri.split('@', 1)
        password = parts_at[0]
        server_info = parts_at[1] if len(parts_at) > 1 else ''

        parts_query = server_info.split('?', 1)
        server_port_str = parts_query[0]
        query_params = {}
        if len(parts_query) > 1:
            for param in parts_query[1].split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value

        server, port = None, None
        if ':' in server_port_str:
            server_parts = server_port_str.rsplit(':', 1)
            server = server_parts[0]
            port = int(server_parts[1])
        
        if not server or not port:
            return None

        proxy = {
            'name': name,
            'type': 'hysteria2',
            'server': server,
            'port': port,
            'password': password,
            'udp': True, # Hysteria2 is UDP-based, but also needs TCP for initial handshake
            'autocert': query_params.get('autocert', '0') == '1',
            'skip-cert-verify': query_params.get('insecure', '0') == '1',
            'servername': query_params.get('sni', server),
            'mfa': query_params.get('mfa', ''), # Multi-factor authentication
            'obfs': query_params.get('obfs', 'none'),
            'obfs-password': query_params.get('obfs-password', '')
        }
        return proxy
    except Exception as e:
        # print(f"Failed to parse Hysteria2 link: {link} - Error: {e}")
        return None

# --- Link Parsing Dispatcher ---
def _parse_single_proxy_link(link):
    """Dispatches parsing based on link scheme."""
    if link.startswith("vmess://"):
        return parse_vmess(link)
    elif link.startswith("trojan://"):
        return parse_trojan(link)
    elif link.startswith("ss://"):
        return parse_shadowsocks(link)
    elif link.startswith("hysteria2://"):
        return parse_hysteria2(link)
    # Add other protocols as needed
    return None

def _try_parse_yaml_proxies(decoded_text):
    """Attempts to parse a YAML string containing a list of Clash proxies."""
    try:
        parsed_yaml = yaml.safe_load(decoded_text)
        if isinstance(parsed_yaml, dict) and 'proxies' in parsed_yaml and isinstance(parsed_yaml['proxies'], list):
            # Basic validation to ensure it looks like a proxy list
            if parsed_yaml['proxies'] and isinstance(parsed_yaml['proxies'][0], dict) and 'name' in parsed_yaml['proxies'][0]:
                print(f"Identified as YAML subscription, found {len(parsed_yaml['proxies'])} proxies")
                return parsed_yaml['proxies']
    except yaml.YAMLError:
        pass
    return None

def _try_parse_v2rayn_json_proxies(decoded_text):
    """Attempts to parse a V2RayN-style JSON array of Vmess configs."""
    try:
        parsed_json = json.loads(decoded_text)
        if isinstance(parsed_json, list):
            # Check if it looks like a list of Vmess objects (heuristic)
            if all(isinstance(item, dict) and 'v' in item and 'ps' in item and 'add' in item for item in parsed_json):
                print(f"Identified as V2RayN JSON subscription, found {len(parsed_json)} proxies")
                proxies = []
                for vmess_config in parsed_json:
                    proxy = {
                        'name': vmess_config.get('ps', vmess_config.get('id', 'vmess_node')),
                        'type': 'vmess',
                        'server': vmess_config.get('add'),
                        'port': int(vmess_config.get('port')),
                        'uuid': vmess_config.get('id'),
                        'alterId': int(vmess_config.get('aid', 0)),
                        'cipher': vmess_config.get('scy', 'auto'),
                        'udp': True,
                        'network': vmess_config.get('net', 'tcp'),
                    }
                    if vmess_config.get('tls') == 'tls':
                        proxy['tls'] = True
                        proxy['skip-cert-verify'] = vmess_config.get('v', '') != '2' and vmess_config.get('sni') == ''
                        proxy['servername'] = vmess_config.get('host', '') if vmess_config.get('host') else vmess_config.get('sni', '')
                        if proxy['servername'] == '':
                            proxy['servername'] = proxy['server']
                    if proxy['network'] == 'ws':
                        proxy['ws-opts'] = {
                            'path': vmess_config.get('path', '/'),
                            'headers': {'Host': vmess_config.get('host', '')}
                        }
                    elif proxy['network'] == 'grpc':
                        proxy['grpc-opts'] = {
                            'serviceName': vmess_config.get('path', ''),
                            'grpcMode': 'gun' if vmess_config.get('host') == 'gun' else 'direct'
                        }
                    
                    if proxy['server'] and proxy['port']:
                        proxies.append(proxy)
                return proxies
    except json.JSONDecodeError:
        pass
    return None

def _parse_proxies_from_decoded_text(decoded_text, url=""):
    """Parses proxies from a decoded string, trying various formats."""
    # Try parsing as YAML list of proxies first (e.g., Clash subscription)
    yaml_proxies = _try_parse_yaml_proxies(decoded_text)
    if yaml_proxies:
        return yaml_proxies

    # Try parsing as V2RayN-style JSON array
    v2rayn_proxies = _try_parse_v2rayn_json_proxies(decoded_text)
    if v2rayn_proxies:
        return v2rayn_proxies

    # If not YAML or V2RayN JSON, assume it's a list of proxy links (one per line)
    proxies = []
    lines = decoded_text.splitlines()
    for line in lines:
        stripped_line = line.strip()
        if stripped_line:
            proxy = _parse_single_proxy_link(stripped_line)
            if proxy:
                proxies.append(proxy)
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

            # Attempt 1: Try to decode as UTF-8 and parse
            decoded_successfully = False
            try:
                decoded_content_utf8 = content.decode('utf-8')
                decoded_successfully = True
                
                proxies_from_utf8 = _parse_proxies_from_decoded_text(decoded_content_utf8, url)
                if proxies_from_utf8:
                    current_proxies_from_url.extend(proxies_from_utf8)
                else:
                    # If UTF-8 parsing failed, it might be Base64 encoded *within* a UTF-8 string.
                    stripped_content = decoded_content_utf8.strip()
                    if len(stripped_content) > 0 and (len(stripped_content) % 4 == 0 or '=' not in stripped_content) and re.fullmatch(r'[A-Za-z0-9+/=]*', stripped_content):
                        try:
                            # Add padding if necessary, robustly
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

            # Attempt 2: If no proxies found yet, OR initial UTF-8 decoding failed, try direct Base64 decoding of original content
            if not current_proxies_from_url:
                try:
                    cleaned_byte_content = content.strip()
                    # Ensure byte content is a multiple of 4 for base64 decoding
                    missing_padding = len(cleaned_byte_content) % 4
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
                print(f"  --- URL: {url} No proxies successfully parsed from this URL. Content snippet (latin-1, first 100 chars): '{content[:100].decode('latin-1', errors='ignore')}' ---")

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch data from URL: {url}, reason: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing URL {url}: {e}")

    # --- Deduplication and Connectivity Test (Parallelized) ---
    # MODIFIED DEDUPLICATION LOGIC: Use generate_proxy_fingerprint for unique keys
    unique_proxies_for_test = {}
    for proxy_dict in all_raw_proxies:
        if proxy_dict and isinstance(proxy_dict, dict) and 'server' in proxy_dict and 'port' in proxy_dict :
            # Check for exclude keywords in server name (case-insensitive)
            if any(keyword in proxy_dict['server'].lower() for keyword in EXCLUDE_NODES_BY_SERVER):
                # print(f"Excluding node due to server keyword: {proxy_dict['server']}")
                continue

            fingerprint = generate_proxy_fingerprint(proxy_dict)
            if fingerprint not in unique_proxies_for_test:
                unique_proxies_for_test[fingerprint] = proxy_dict
            else:
                # Optional: If a duplicate is found, you might want to log it
                # print(f"    检测到重复节点 (基于核心参数): {proxy_dict.get('name', proxy_dict.get('server'))}")
                pass
            
    proxies_to_test_list = list(unique_proxies_for_test.values())
    final_filtered_proxies = []

    if enable_connectivity_test:
        print(f"\n开始并行连通性测试，共 {len(proxies_to_test_list)} 个唯一代理...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_CONNECTIVITY_TEST) as executor:
            future_to_proxy = {
                executor.submit(test_tcp_connectivity, p['server'], p['port']): p
                for p in proxies_to_test_list if p.get('server') and isinstance(p.get('port'), int)
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
                        # --- START MODIFIED NAMING LOGIC (from previous update, remains) ---
                        original_parsed_name = proxy_dict.get('name', '') # 获取解析函数得到的名称
                        fingerprint_suffix = generate_proxy_fingerprint(proxy_dict)[:8] # 获取指纹

                        if original_parsed_name:
                            # 如果原始名称存在，使用原始名称 + 指纹
                            # 增加一个长度限制，避免名称过长
                            max_name_len = 40 # 原始名称的最大长度，加上指纹和连字符
                            if len(original_parsed_name) > max_name_len:
                                display_name = f"{original_parsed_name[:max_name_len]}..."
                            else:
                                display_name = original_parsed_name
                            proxy_dict['name'] = f"{display_name}-{fingerprint_suffix}"
                        else:
                            # 如果原始名称不存在，则回退到 类型-服务器 + 指纹
                            base_name = f"{proxy_dict.get('type', 'UNKNOWN').upper()}-{proxy_dict.get('server', 'unknown_server')}"
                            proxy_dict['name'] = f"{base_name}-{fingerprint_suffix}"
                        # --- END MODIFIED NAMING LOGIC ---
                        
                        final_filtered_proxies.append(proxy_dict)
                except Exception as exc:
                    print(f"    连通性测试 {server}:{port} 时发生异常: {exc}")
                
                # Print progress every 50 proxies or at the end
                if processed_count % 50 == 0 or processed_count == total_testable_proxies:
                    print(f"    进度: 已测试 {processed_count}/{total_testable_proxies} 个代理...")
    else:
        print("跳过连通性测试 (已禁用)。所有解析出的唯一代理将被添加。")
        for proxy_dict in proxies_to_test_list:
            # --- START MODIFIED NAMING LOGIC (for when connectivity test is disabled, remains) ---
            original_parsed_name = proxy_dict.get('name', '')
            fingerprint_suffix = generate_proxy_fingerprint(proxy_dict)[:8]

            if original_parsed_name:
                max_name_len = 40
                if len(original_parsed_name) > max_name_len:
                    display_name = f"{original_parsed_name[:max_name_len]}..."
                else:
                    display_name = original_parsed_name
                proxy_dict['name'] = f"{display_name}-{fingerprint_suffix}"
            else:
                base_name = f"{proxy_dict.get('type', 'UNKNOWN').upper()}-{proxy_dict.get('server', 'unknown_server')}"
                proxy_dict['name'] = f"{base_name}-{fingerprint_suffix}"
            # --- END MODIFIED NAMING LOGIC ---
            final_filtered_proxies.append(proxy_dict)

    print(f"Successfully parsed, deduplicated, tested, and aggregated {len(final_filtered_proxies)} unique and reachable proxy nodes.")
    return final_filtered_proxies, list(successful_urls)

# --- GitHub API Helpers ---
def get_github_file_content(repo_api_url):
    """Fetches content of a file from GitHub API and its SHA."""
    headers = {
        'Accept': 'application/vnd.github.v3.raw',
        'User-Agent': 'GitHubActions/Aggregator' # Good practice to set User-Agent
    }
    # For public repos, token is usually not needed for content.
    # If it's a private repo or hits rate limit, consider adding Authorization header:
    # if os.getenv('GITHUB_TOKEN'):
    #     headers['Authorization'] = f"token {os.getenv('GITHUB_TOKEN')}"

    print(f"DEBUG: 尝试从 GitHub API 获取文件: {repo_api_url}")
    response = requests.get(repo_api_url, headers=headers, timeout=10)
    print(f"DEBUG: GitHub API 响应状态码: {response.status_code}")
    response.raise_for_status() # Raise an exception for HTTP errors
    
    # Get SHA from ETag or Link header
    sha = response.headers.get('ETag', '').strip('"') # ETag usually contains SHA for blobs
    if not sha:
        # Fallback for SHA if ETag is not the SHA directly, or if it's a tree/commit SHA
        # This is less reliable for blob content SHA, but might be needed if API changes
        print("DEBUG: X-GitHub-Sha 为 None，从 ETag 获取到 SHA: " + sha)
    else:
         print("DEBUG: 从 ETag 获取到 SHA: " + sha)
         
    return response.text, sha # Return text content and SHA

def update_github_file_content(repo_api_url, content, sha, commit_message, bot_token):
    """Updates a file on GitHub via API."""
    headers = {
        'Authorization': f"token {bot_token}",
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'GitHubActions/Aggregator'
    }
    data = {
        'message': commit_message,
        'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
        'sha': sha
    }
    print(f"DEBUG: 尝试更新 GitHub 文件: {repo_api_url} with SHA: {sha}")
    response = requests.put(repo_api_url, headers=headers, json=data, timeout=10)
    print(f"DEBUG: GitHub API 更新响应状态码: {response.status_code}")
    response.raise_for_status()
    return response.json()


# --- Main Function ---
def main():
    if not URL_LIST_REPO_API:
        print("Error: URL_LIST_REPO_API environment variable is not set. Exiting.")
        sys.exit(1)

    url_list_content, url_list_sha = get_github_file_content(URL_LIST_REPO_API)
    subscription_urls = [url.strip() for url in url_list_content.splitlines() if url.strip()]
    
    print(f"Fetched {len(subscription_urls)} non-empty subscription URLs from GitHub.")

    # Load Clash template
    try:
        with open(CLASH_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            clash_template = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Clash template file not found at {CLASH_TEMPLATE_PATH}. Exiting.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing Clash template YAML: {e}. Exiting.")
        sys.exit(1)

    # Fetch and process proxies
    filtered_proxies, successful_urls_set = fetch_and_decode_urls_to_clash_proxies(
        subscription_urls,
        enable_connectivity_test=ENABLE_CONNECTIVITY_TEST
    )

    # Convert proxies to YAML format
    proxies_yaml = yaml.dump(filtered_proxies, sort_keys=False, indent=2, allow_unicode=True)
    
    # Generate Clash config file
    clash_config = clash_template
    clash_config['proxies'] = filtered_proxies
    
    # Generate proxy groups based on the filtered proxies (simplified example)
    # This part would need more sophisticated logic for robust group creation
    # For now, let's just make a simple 'Auto' group that uses all available proxies
    proxy_names = [p['name'] for p in filtered_proxies]
    if 'proxy-groups' not in clash_config:
        clash_config['proxy-groups'] = []

    # Example: Add an 'Auto' group and 'Proxy' group if they don't exist
    auto_group_exists = False
    proxy_group_exists = False
    
    for group in clash_config['proxy-groups']:
        if group.get('name') == 'Auto':
            group['proxies'] = ['DIRECT'] + proxy_names # Add DIRECT for fallback
            auto_group_exists = True
        if group.get('name') == 'Proxy':
            # This 'Proxy' group typically points to 'Auto' or similar
            group['proxies'] = ['Auto', 'DIRECT'] # Ensure it has correct fallback/selection
            proxy_group_exists = True

    if not auto_group_exists:
        clash_config['proxy-groups'].append({
            'name': 'Auto',
            'type': 'select',
            'proxies': ['DIRECT'] + proxy_names
        })
    if not proxy_group_exists:
         clash_config['proxy-groups'].append({
            'name': 'Proxy',
            'type': 'select',
            'proxies': ['Auto', 'DIRECT']
        })

    # The rules section in the template should be adjusted by the user as needed.
    # Here, we ensure that the main proxy group is at least part of the rules.
    # This is a very basic example and might need adjustment for complex rule sets.
    if 'rules' in clash_config:
        # Ensure a final DIRECT rule exists if not already present
        if 'MATCH,DIRECT' not in clash_config['rules'] and 'FINAL,DIRECT' not in clash_config['rules']:
            clash_config['rules'].append('MATCH,DIRECT')


    # Write to base64.yaml
    with open('base64.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(clash_config, f, sort_keys=False, indent=2, allow_unicode=True)
    print("Generated base64.yaml (Clash config).")

    # Generate base64.txt (Base64 encoded YAML)
    with open('base64.yaml', 'r', encoding='utf-8') as f:
        config_content = f.read()
    base64_content = base64.b64encode(config_content.encode('utf-8')).decode('utf-8')
    with open('base64.txt', 'w', encoding='utf-8') as f:
        f.write(base64_content)
    print("Generated base64.txt (Base64 encoded Clash config).")

    # Optional: Update URL list on GitHub if needed (e.g., remove failed URLs)
    # This logic is commented out by default but can be enabled if needed
    # (Requires BOT secret and URL_LIST_REPO_API pointing to the actual URL list file)
    # bot_token = os.getenv('BOT')
    # if bot_token and URL_LIST_REPO_API:
    #     current_url_list = set(subscription_urls)
    #     urls_to_keep = sorted(list(successful_urls_set.intersection(current_url_list)))
    #     if len(urls_to_keep) < len(current_url_list):
    #         print(f"Updating URL list on GitHub: keeping {len(urls_to_keep)} of {len(current_url_list)} URLs.")
    #         new_url_list_content = "\n".join(urls_to_keep) + "\n"
    #         if new_url_list_content.strip() != url_list_content.strip():
    #             try:
    #                 update_github_file_content(URL_LIST_REPO_API, new_url_list_content, url_list_sha,
    #                                            "chore: Update subscription URLs based on successful fetches", bot_token)
    #                 print("Successfully updated subscription URL list on GitHub.")
    #             except requests.exceptions.RequestException as e:
    #                 print(f"Failed to update subscription URL list on GitHub: {e}")
    #             except Exception as e:
    #                 print(f"An unexpected error occurred while updating URL list: {e}")
    #         else:
    #             print("No changes to subscription URL list, skipping GitHub update.")
    #     else:
    #         print("All URLs were successfully fetched, no need to update URL list on GitHub.")
    # else:
    #     print("Skipping URL list update on GitHub (BOT secret or URL_LIST_REPO_API not set).")


if __name__ == "__main__":
    main()
