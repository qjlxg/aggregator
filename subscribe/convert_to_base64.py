import requests
import base64
import os
import json
import re
import yaml
from urllib.parse import urlparse, parse_qs, unquote, quote
import hashlib
import socket
import time
import concurrent.futures
import logging
import ipaddress
import maxminddb

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%-Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

GEOIP_READER = None

def init_geoip_reader(db_path):
    global GEOIP_READER
    if not os.path.exists(db_path):
        logger.warning(f"GeoIP 数据库文件未找到: {db_path}。GeoIP 过滤将禁用。")
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
    if GEOIP_READER is None:
        return None
    try:
        ipaddress.ip_address(ip_address)
        record = GEOIP_READER.get(ip_address)
        if record and 'country' in record and 'iso_code' in record['country']:
            return record['country']['iso_code']
        return None
    except ValueError:
        return None
    except Exception as e:
        logger.warning(f"GeoIP 查找 IP 地址 '{ip_address}' 时发生错误: {e}")
        return None

CHINA_KEYWORDS = [
    "中国", "china", "cn", "🇨🇳",
    "ch", "mainland", "domestic",
    ".cn", ".com.cn", ".net.cn", ".org.cn",
    "aliyun", "tencentcloud", "huaweicloud",
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu",
    "移动", "联通", "电信",
    "cmcc", "unicom", "telecom",
]

def is_likely_china_node(proxy_data):
    name_lower = proxy_data.get('name', '').lower()
    server = proxy_data.get('server', '')
    server_lower = server.lower()

    if GEOIP_READER is not None:
        try:
            server_ip = socket.gethostbyname(server)
            country_code = get_country_code(server_ip)
            if country_code == 'CN':
                logger.debug(f"  节点 '{proxy_data.get('name')}' (IP: {server_ip}) 经 GeoIP 确认位于中国，已排除。")
                return True
            elif country_code is not None:
                logger.debug(f"  节点 '{proxy_data.get('name')}' (IP: {server_ip}) 位于 {country_code}。")
            else:
                logger.debug(f"  无法通过 GeoIP 确定 IP '{server_ip}' 的国家，尝试关键词匹配。")
        except socket.gaierror:
            logger.debug(f"  无法解析服务器 '{server}' 的 IP，跳过 GeoIP 检查，尝试关键词匹配。")
        except Exception as e:
            logger.error(f"GeoIP 检查 '{server}' 时发生错误: {e}，尝试关键词匹配。")
    else:
        logger.debug(f"  GeoIP 数据库未加载或初始化失败，将仅依赖关键词过滤。")
    
    for keyword in CHINA_KEYWORDS:
        if keyword in name_lower or keyword in server_lower:
            logger.debug(f"  节点 '{proxy_data.get('name')}' 因关键词 '{keyword}' 被排除。")
            return True

    return False

def generate_proxy_fingerprint(proxy_data):
    parts = []
    
    parts.append(str(proxy_data.get('type', '')))
    parts.append(str(proxy_data.get('server', '')))
    parts.append(str(proxy_data.get('port', '')))
    parts.append(str(proxy_data.get('tls', False)))
    parts.append(str(proxy_data.get('servername', '')))

    node_type = proxy_data.get('type')

    if node_type == 'vmess':
        parts.append(str(proxy_data.get('uuid', '')))
        parts.append(str(proxy_data.get('alterId', 0)))
        parts.append(str(proxy_data.get('cipher', 'auto')))
        parts.append(str(proxy_data.get('network', 'tcp')))

        network = proxy_data.get('network')
        if network == 'ws':
            parts.append(str(proxy_data.get('ws-path', '/')))
            if proxy_data.get('ws-headers') and proxy_data['ws-headers'].get('Host'):
                parts.append(str(proxy_data['ws-headers']['Host']))
        elif network == 'grpc':
            parts.append(str(proxy_data.get('grpc-service-name', '')))
        
        if proxy_data.get('alpn'):
            parts.append(str(proxy_data['alpn']))

    elif node_type == 'trojan':
        parts.append(str(proxy_data.get('password', '')))
        if proxy_data.get('network') == 'ws':
            parts.append(str(proxy_data.get('network')))
            parts.append(str(proxy_data.get('ws-path', '/')))
            if proxy_data.get('ws-headers') and proxy_data['ws-headers'].get('Host'):
                parts.append(str(proxy_data['ws-headers']['Host']))
        if proxy_data.get('alpn'):
            parts.append(str(proxy_data['alpn']))
        if proxy_data.get('flow'):
            parts.append(str(proxy_data['flow']))

    elif node_type == 'ss':
        parts.append(str(proxy_data.get('cipher', '')))
        parts.append(str(proxy_data.get('password', '')))
        if proxy_data.get('plugin'):
            parts.append(str(proxy_data['plugin']))
            if proxy_data.get('plugin-opts'):
                sorted_opts = sorted(proxy_data['plugin-opts'].items())
                parts.append(str(sorted_opts))

    elif node_type == 'ssr':
        parts.append(str(proxy_data.get('password', '')))
        parts.append(str(proxy_data.get('cipher', '')))
        parts.append(str(proxy_data.get('protocol', 'origin')))
        parts.append(str(proxy_data.get('protocolparam', '')))
        parts.append(str(proxy_data.get('obfs', 'plain')))
        parts.append(str(proxy_data.get('obfsparam', '')))

    elif node_type == 'hysteria2':
        parts.append(str(proxy_data.get('password', '')))
        parts.append(str(proxy_data.get('fast-open', False)))
        if proxy_data.get('alpn'):
            parts.append(str(proxy_data['alpn']))
        if proxy_data.get('fingerprint'):
            parts.append(str(proxy_data['fingerprint']))
    
    elif node_type == 'hysteria':
        parts.append(str(proxy_data.get('password', '')))
        parts.append(str(proxy_data.get('auth_str', '')))
        parts.append(str(proxy_data.get('alpn', '')))
        parts.append(str(proxy_data.get('fast-open', False)))
        parts.append(str(proxy_data.get('up', 0)))
        parts.append(str(proxy_data.get('down', 0)))
        parts.append(str(proxy_data.get('obfs', 'none')))
        parts.append(str(proxy_data.get('obfs-uri', '')))
        if proxy_data.get('fingerprint'):
            parts.append(str(proxy_data['fingerprint']))

    elif node_type == 'tuic':
        parts.append(str(proxy_data.get('uuid', '')))
        parts.append(str(proxy_data.get('password', ''))) # TUIC 的密码就是 UUID
        parts.append(str(proxy_data.get('congestion-controller', 'bbr')))
        parts.append(str(proxy_data.get('udp-relay-mode', 'quic')))
        parts.append(str(proxy_data.get('disable-sni', False)))
        if proxy_data.get('alpn'):
            parts.append(str(proxy_data['alpn']))
        if proxy_data.get('fingerprint'):
            parts.append(str(proxy_data['fingerprint']))
        if proxy_data.get('flow'):
            parts.append(str(proxy_data['flow']))
        if proxy_data.get('zero-rtt'):
            parts.append(str(proxy_data['zero-rtt']))

    elif node_type == 'vless':
        parts.append(str(proxy_data.get('uuid', '')))
        parts.append(str(proxy_data.get('network', 'tcp')))
        parts.append(str(proxy_data.get('tls', False)))
        parts.append(str(proxy_data.get('servername', '')))
        if proxy_data.get('flow'):
            parts.append(str(proxy_data['flow']))

        network = proxy_data.get('network')
        if network == 'ws':
            parts.append(str(proxy_data.get('ws-path', '/')))
            if proxy_data.get('ws-headers') and proxy_data['ws-headers'].get('Host'):
                parts.append(str(proxy_data['ws-headers']['Host']))
        elif network == 'grpc':
            parts.append(str(proxy_data.get('grpc-service-name', '')))
            parts.append(str(proxy_data.get('grpc-auto-commit', False)))
        
        if proxy_data.get('alpn'):
            parts.append(str(proxy_data['alpn']))
        if proxy_data.get('fingerprint'):
            parts.append(str(proxy_data['fingerprint']))
        if proxy_data.get('reality-opts') and proxy_data['reality-opts'].get('public-key'):
            parts.append(str(proxy_data['reality-opts']['public-key']))
        if proxy_data.get('xudp-opts') and proxy_data['xudp-opts'].get('udp-over-tcp'):
            parts.append(str(proxy_data['xudp-opts']['udp-over-tcp']))

    unique_string = "_".join(sorted(parts))
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
        elif network == 'grpc':
            proxy['grpc-service-name'] = config.get('serviceName', '')

        if config.get('alpn'):
            proxy['alpn'] = config['alpn']

        return proxy
    except Exception as e:
        logger.debug(f"解析 Vmess 链接失败: {vmess_url[:50]}...，原因: {e}")
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
        
        if params.get('flow'):
            proxy['flow'] = params['flow'][0]

        if params.get('alpn'):
            alpn_list = params['alpn'][0].split(',')
            proxy['alpn'] = alpn_list if len(alpn_list) > 1 else alpn_list[0]

        if params.get('type', [''])[0] == 'ws':
            proxy['network'] = 'ws'
            proxy['ws-path'] = params.get('path', ['/'])[0]
            if params.get('host'):
                proxy['ws-headers'] = {"Host": params['host'][0]}

        return proxy
    except Exception as e:
        logger.debug(f"解析 Trojan 链接失败: {trojan_url[:50]}...，原因: {e}")
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
        elif '?' in encoded_part and 'obfs=' in encoded_part: # Handle SIP002 plugin options
            parts = encoded_part.split('?', 1)
            encoded_part = parts[0]
            query_params = parse_qs(parts[1])
            if 'plugin' in query_params:
                plugin_info_str = unquote(query_params['plugin'][0])
                if 'plugin_opts' in query_params:
                    plugin_info_str += ';' + unquote(query_params['plugin_opts'][0])

        missing_padding = len(encoded_part) % 4
        if missing_padding:
            encoded_part += '=' * (4 - missing_padding)
        
        try:
            decoded_bytes = base64.urlsafe_b64decode(encoded_part)
            decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
            
            match = re.match(r'^([^:]+):([^@]+)@([^:]+):(\d+)$', decoded_str)
            if not match:
                match = re.match(r'^([^@]+)@([^:]+):(\d+)$', decoded_str)
                if match:
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
        logger.debug(f"解析 Shadowsocks 链接失败: {ss_url[:100]}...，原因: {e}")
        return None

def parse_ssr(ssr_url):
    try:
        encoded_part = ssr_url[6:]
        missing_padding = len(encoded_part) % 4
        if missing_padding:
            encoded_part += '=' * (4 - missing_padding)
        
        decoded_bytes = base64.urlsafe_b64decode(encoded_part)
        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')

        main_part, params_str = (decoded_str.split('/?', 1) + [''])[:2]
        
        parts = main_part.split(':')
        if len(parts) < 6:
            raise ValueError(f"SSR 链接主体部分不足6个字段: {main_part}")

        server = parts[0]
        port = int(parts[1])
        protocol = parts[2]
        cipher = parts[3]
        obfs = parts[4]
        password_b64_padded = parts[5] + '=' * (4 - len(parts[5]) % 4)
        password = base64.urlsafe_b64decode(password_b64_padded).decode('utf-8', errors='ignore')

        params = parse_qs(params_str)
        
        protocolparam_b64 = params.get('protoparam', [''])[0]
        protocolparam = base64.urlsafe_b64decode(protocolparam_b64 + '=' * (4 - len(protocolparam_b64) % 4)).decode('utf-8', errors='ignore') if protocolparam_b64 else ''

        obfsparam_b64 = params.get('obfsparam', [''])[0]
        obfsparam = base64.urlsafe_b64decode(obfsparam_b64 + '=' * (4 - len(obfsparam_b64) % 4)).decode('utf-8', errors='ignore') if obfsparam_b64 else ''

        remarks_b64 = params.get('remarks', [''])[0]
        name = base64.urlsafe_b64decode(remarks_b64 + '=' * (4 - len(remarks_b64) % 4)).decode('utf-8', errors='ignore') if remarks_b64 else f"SSR-{server}"

        group_b64 = params.get('group', [''])[0]
        group = base64.urlsafe_b64decode(group_b64 + '=' * (4 - len(group_b64) % 4)).decode('utf-8', errors='ignore') if group_b64 else ''

        proxy = {
            'name': name,
            'type': 'ssr',
            'server': server,
            'port': port,
            'cipher': cipher,
            'password': password,
            'protocol': protocol,
            'protocolparam': protocolparam,
            'obfs': obfs,
            'obfsparam': obfsparam,
        }
        if group:
            proxy['group'] = group
        
        return proxy

    except Exception as e:
        logger.debug(f"解析 ShadowsocksR 链接失败: {ssr_url[:100]}...，原因: {e}")
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
        alpn_str = params.get('alpn', [''])[0]
        alpn = alpn_str.split(',') if alpn_str else []
        
        fingerprint = params.get('fp', [''])[0]

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
        if alpn:
            proxy['alpn'] = alpn
        if fingerprint:
            proxy['fingerprint'] = fingerprint

        return proxy
    except Exception as e:
        logger.debug(f"解析 Hysteria2 链接失败: {hy2_url[:50]}...，原因: {e}")
        return None

def parse_hysteria(hy_url):
    try:
        parsed = urlparse(hy_url)
        password = parsed.username
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"Hysteria-{server}"

        params = parse_qs(parsed.query)
        tls = params.get('tls', ['0'])[0] == '1'
        servername = params.get('sni', [''])[0]
        skip_cert_verify = params.get('insecure', ['0'])[0] == '1'
        fast_open = params.get('fastopen', ['0'])[0] == '1'
        alpn_str = params.get('alpn', [''])[0]
        alpn = alpn_str.split(',') if alpn_str else []
        
        up_mbps = int(params.get('up', ['0'])[0])
        down_mbps = int(params.get('down', ['0'])[0])
        auth_str = params.get('auth', [''])[0]

        obfs = params.get('obfs', ['none'])[0]
        obfs_uri = params.get('obfs-uri', [''])[0]
        fingerprint = params.get('fp', [''])[0]

        proxy = {
            'name': name,
            'type': 'hysteria',
            'server': server,
            'port': port,
            'password': password,
            'tls': tls,
            'skip-cert-verify': skip_cert_verify,
            'fast-open': fast_open,
            'up': up_mbps,
            'down': down_mbps,
            'obfs': obfs,
            'obfs-uri': obfs_uri,
        }
        if servername:
            proxy['servername'] = servername
        if alpn:
            proxy['alpn'] = alpn
        if auth_str:
            proxy['auth_str'] = auth_str
        if fingerprint:
            proxy['fingerprint'] = fingerprint

        return proxy
    except Exception as e:
        logger.debug(f"解析 Hysteria 链接失败: {hy_url[:50]}...，原因: {e}")
        return None

def parse_tuic(tuic_url):
    try:
        parsed = urlparse(tuic_url)
        uuid = parsed.username
        password = parsed.password
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"TUIC-{server}"

        params = parse_qs(parsed.query)
        tls = params.get('tls', ['0'])[0] == '1'
        servername = params.get('sni', [''])[0]
        skip_cert_verify = params.get('insecure', ['0'])[0] == '1'
        congestion_controller = params.get('cc', ['bbr'])[0]
        udp_relay_mode = params.get('udp_relay_mode', ['quic'])[0]
        disable_sni = params.get('disable_sni', ['0'])[0] == '1'
        alpn_str = params.get('alpn', [''])[0]
        alpn = alpn_str.split(',') if alpn_str else []
        fingerprint = params.get('fingerprint', [''])[0]
        flow = params.get('flow', [''])[0]
        zero_rtt = params.get('0-rtt', ['0'])[0] == '1'

        proxy = {
            'name': name,
            'type': 'tuic',
            'server': server,
            'port': port,
            'uuid': uuid,
            'password': password if password else uuid,
            'tls': tls,
            'skip-cert-verify': skip_cert_verify,
            'congestion-controller': congestion_controller,
            'udp-relay-mode': udp_relay_mode,
            'disable-sni': disable_sni,
            'zero-rtt': zero_rtt,
        }
        if servername:
            proxy['servername'] = servername
        if alpn:
            proxy['alpn'] = alpn
        if fingerprint:
            proxy['fingerprint'] = fingerprint
        if flow:
            proxy['flow'] = flow

        return proxy
    except Exception as e:
        logger.debug(f"解析 TUIC 链接失败: {tuic_url[:50]}...，原因: {e}")
        return None

def parse_vless(vless_url):
    try:
        parsed = urlparse(vless_url)
        uuid = parsed.username
        server = parsed.hostname
        port = parsed.port
        name = unquote(parsed.fragment) if parsed.fragment else f"VLESS-{server}"

        params = parse_qs(parsed.query)
        
        tls = params.get('security', [''])[0] == 'tls'
        servername = params.get('sni', [''])[0]
        skip_cert_verify = params.get('allowInsecure', ['0'])[0] == '1'
        flow = params.get('flow', [''])[0]
        network = params.get('type', ['tcp'])[0]
        alpn_str = params.get('alpn', [''])[0]
        alpn = alpn_str.split(',') if alpn_str else []
        fingerprint = params.get('fp', [''])[0]

        proxy = {
            'name': name,
            'type': 'vless',
            'server': server,
            'port': port,
            'uuid': uuid,
            'network': network,
            'tls': tls,
            'skip-cert-verify': skip_cert_verify,
        }
        if servername:
            proxy['servername'] = servername
        if flow:
            proxy['flow'] = flow
        if alpn:
            proxy['alpn'] = alpn
        if fingerprint:
            proxy['fingerprint'] = fingerprint
        
        if network == 'ws':
            proxy['ws-path'] = params.get('path', ['/'])[0]
            if params.get('host'):
                proxy['ws-headers'] = {"Host": params['host'][0]}
        elif network == 'grpc':
            proxy['grpc-service-name'] = params.get('serviceName', [''])[0]
            proxy['grpc-auto-commit'] = params.get('grpcAutoCommit', ['0'])[0] == '1'

        return proxy
    except Exception as e:
        logger.debug(f"解析 VLESS 链接失败: {vless_url[:50]}...，原因: {e}")
        return None


EXCLUDE_URL_KEYWORDS = [
    "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
    "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net",
    "t.me", "api.w.org", "html", "css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp", "xml", "json", "txt",
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

def download_and_parse_single_url(url):
    url = url.strip()
    if not url or any(keyword in url for keyword in EXCLUDE_URL_KEYWORDS):
        logger.debug(f"跳过非订阅链接 (被关键词过滤): {url}")
        return [], False

    logger.info(f"  正在获取: {url}")
    parsed_proxies = []
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

        decoded_content = None
        try:
            decoded_content = content.decode('utf-8')
        except UnicodeDecodeError:
            logger.debug(f"    URL: {url} UTF-8 解码失败，尝试 Base64。")
            try:
                cleaned_content = content.strip()
                if len(cleaned_content) > 0 and len(cleaned_content) % 4 == 0 and re.fullmatch(r'[A-Za-z0-9+/=]*', cleaned_content):
                    decoded_content = base64.b64decode(cleaned_content).decode('utf-8')
                    logger.debug(f"    URL: {url} Base64 解码成功。")
                else:
                    logger.debug(f"    URL: {url} 看起来不像有效 Base64，跳过。")
            except (base64.binascii.Error, UnicodeDecodeError) as e:
                logger.debug(f"    URL: {url} Base64 解码失败: {e}")
                decoded_content = content.decode('latin-1', errors='ignore')
                logger.warning(f"    警告：无法将 {url} 的内容解码为 UTF-8 或 Base64。使用 latin-1。")

        if decoded_content:
            yaml_proxies = try_parse_yaml(decoded_content)
            if yaml_proxies:
                parsed_proxies.extend(yaml_proxies)
                logger.info(f"    URL: {url} 识别为 YAML 订阅，包含 {len(yaml_proxies)} 个代理。")
            else:
                json_proxies = try_parse_json_nodes(decoded_content)
                if json_proxies:
                    parsed_proxies.extend(json_proxies)
                    logger.info(f"    URL: {url} 识别为 JSON 节点列表，包含 {len(json_proxies)} 个代理。")
                else:
                    lines = decoded_content.split('\n')
                    line_parsed_count = 0
                    for line in lines:
                        line = line.strip()
                        p = None
                        if line.startswith("vmess://"): p = parse_vmess(line)
                        elif line.startswith("trojan://"): p = parse_trojan(line)
                        elif line.startswith("ss://"): p = parse_shadowsocks(line)
                        elif line.startswith("ssr://"): p = parse_ssr(line)
                        elif line.startswith("hysteria2://"): p = parse_hysteria2(line)
                        elif line.startswith("hysteria://"): p = parse_hysteria(line)
                        elif line.startswith("tuic://"): p = parse_tuic(line)
                        elif line.startswith("vless://"): p = parse_vless(line)
                        if p: parsed_proxies.append(p); line_parsed_count += 1
                    if line_parsed_count > 0:
                        logger.info(f"    URL: {url} 识别为 {line_parsed_count} 个代理节点。")
                    else:
                        logger.warning(f"    URL: {url} 内容未被识别为有效代理格式。")
        else:
             logger.warning(f"    URL: {url} 内容无法解码或为空。")

        return parsed_proxies, True

    except requests.exceptions.RequestException as e:
        logger.error(f"  获取 URL 失败: {url}，原因: {e}")
        return [], False
    except Exception as e:
        logger.error(f"  处理 URL {url} 时发生意外错误: {e}")
        return [], False

def fetch_all_proxies_from_urls(urls):
    all_raw_proxies = []
    successful_urls = set()
    
    max_workers = int(os.environ.get("MAX_SUBSCRIPTION_WORKERS", 10))
    logger.info(f"\n--- 阶段 1/4: 并行下载和解析订阅 (最大 {max_workers} 个并发) ---")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(download_and_parse_single_url, url): url for url in urls}
        
        processed_count = 0
        total_urls = len(urls)
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            processed_count += 1
            try:
                proxies, success = future.result()
                if success:
                    all_raw_proxies.extend(proxies)
                    successful_urls.add(url)
                else:
                    logger.warning(f"    URL: {url} 解析失败或为空，可能没有获取到有效代理。")
            except Exception as exc:
                logger.error(f"    URL: {url} 处理时发生异常: {exc}")

    logger.info(f"--- 阶段 1/4 完成: 成功从 {len(successful_urls)} 个 URL 获取到 {len(all_raw_proxies)} 个原始代理。 ---")
    return all_raw_proxies, list(successful_urls)

def test_tcp_connectivity(server, port, timeout=1, retries=1, delay=0.5):
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
            return True, time.time() - start_time
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            logger.debug(f"  连接尝试 {i+1}/{retries+1} 失败 for {server}:{port} - {e}")
            if i < retries:
                time.sleep(delay)
        except Exception as e:
            logger.error(f"  TCP连接测试发生未知错误: {server}:{port} - {e}")
            return False, float('inf')
    return False, float('inf')

def generate_vmess_link(node):
    vmess_config = {
        "v": "2",
        "ps": node.get("name", "VMESS_Node"),
        "add": node["server"],
        "port": node["port"],
        "id": node["uuid"],
        "aid": node.get("alterId", 0),
        "net": node.get("network", "tcp"),
        "type": "none",
        "host": node.get("ws-headers", {}).get("Host") or node.get("servername", ""),
        "path": node.get("ws-path", "/"),
        "tls": "tls" if node.get("tls") else ""
    }
    if node.get("scy"):
        vmess_config["scy"] = node["scy"]
    if node.get("alpn"):
        vmess_config["alpn"] = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
    if node.get("grpc-service-name"):
        vmess_config["serviceName"] = node["grpc-service-name"]
    if node.get("skip-cert-verify"):
        vmess_config["v"] = "1"
    return "vmess://" + base64.b64encode(json.dumps(vmess_config, ensure_ascii=False).encode('utf-8')).decode('utf-8')

def generate_trojan_link(node):
    params = []
    if node.get("servername"):
        params.append(f"sni={quote(node['servername'])}")
    if node.get("skip-cert-verify"):
        params.append("allowInsecure=1")
    if node.get("alpn"):
        alpn_str = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
        params.append(f"alpn={quote(alpn_str)}")
    
    if node.get("network") == "ws":
        params.append("type=ws")
        ws_path = node.get("ws-path", "/")
        params.append(f"path={quote(ws_path)}")
        if node.get("ws-headers") and node["ws-headers"].get("Host"):
            params.append(f"host={quote(node['ws-headers']['Host'])}")
    
    if node.get("flow"):
        params.append(f"flow={quote(node['flow'])}")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str
    
    remark = quote(node.get("name", "Trojan_Node"))
    return f"trojan://{node['password']}@{node['server']}:{node['port']}{param_str}#{remark}"

def generate_ss_link(node):
    auth_str = f"{node['cipher']}:{node['password']}@{node['server']}:{node['port']}"
    encoded_auth_str = base64.urlsafe_b64encode(auth_str.encode('utf-8')).decode('utf-8').rstrip('=')

    link = f"ss://{encoded_auth_str}"

    if node.get('plugin') and node.get('plugin-opts'):
        plugin_opts_list = [f"{key}={value}" for key, value in node['plugin-opts'].items()]
        plugin_opts_str = ";".join(plugin_opts_list)
        full_plugin_str = f"{node['plugin']};{plugin_opts_str}" if plugin_opts_str else node['plugin']
        link += f"/?plugin={quote(full_plugin_str)}"
    
    remark = quote(node.get("name", "SS_Node"))
    link += f"#{remark}"
    return link

def generate_ssr_link(node):
    protocol = node.get('protocol', 'origin')
    obfs = node.get('obfs', 'plain')
    password = node.get('password', '')

    password_b64 = base64.urlsafe_b64encode(password.encode('utf-8')).decode('utf-8').rstrip('=')

    ssr_str_parts = [
        node['server'],
        str(node['port']),
        protocol,
        node.get('cipher', ''),
        obfs,
        password_b64
    ]
    ssr_str = ":".join(ssr_str_parts)
    
    ssr_params = []
    if node.get("obfsparam"):
        obfsparam_b64 = base64.urlsafe_b64encode(node['obfsparam'].encode('utf-8')).decode('utf-8').rstrip('=')
        ssr_params.append(f"obfsparam={obfsparam_b64}")
    if node.get("protocolparam"):
        protoparam_b64 = base64.urlsafe_b64encode(node['protocolparam'].encode('utf-8')).decode('utf-8').rstrip('=')
        ssr_params.append(f"protoparam={protoparam_b64}")
    
    if node.get("name"):
        remarks_b64 = base64.urlsafe_b64encode(node['name'].encode('utf-8')).decode('utf-8').rstrip('=')
        ssr_params.append(f"remarks={remarks_b64}")
    if node.get("group"):
        group_b64 = base64.urlsafe_b64encode(node['group'].encode('utf-8')).decode('utf-8').rstrip('=')
        ssr_params.append(f"group={group_b64}")
    
    if ssr_params:
        ssr_str += "/?" + "&".join(ssr_params)
        
    return "ssr://" + base64.urlsafe_b64encode(ssr_str.encode('utf-8')).decode('utf-8').rstrip('=')

def generate_hysteria2_link(node):
    params = []
    if node.get('tls'):
        params.append("security=tls")
    if node.get('servername'):
        params.append(f"sni={quote(node['servername'])}")
    if node.get('skip-cert-verify'):
        params.append("insecure=1")
    if node.get('fast-open'):
        params.append("fastopen=1")
    if node.get('alpn'):
        alpn_str = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
        params.append(f"alpn={quote(alpn_str)}")
    if node.get('fingerprint'):
        params.append(f"fp={quote(node['fingerprint'])}")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str
    
    remark = quote(node.get("name", "Hysteria2_Node"))
    return f"hysteria2://{node['password']}@{node['server']}:{node['port']}{param_str}#{remark}"

def generate_hysteria_link(node):
    params = []
    if node.get('password'):
        params.append(f"auth={quote(node['password'])}") # Hysteria V1 用auth
    if node.get('tls'):
        params.append("tls=1")
    if node.get('servername'):
        params.append(f"sni={quote(node['servername'])}")
    if node.get('skip-cert-verify'):
        params.append("insecure=1")
    if node.get('fast-open'):
        params.append("fastopen=1")
    if node.get('alpn'):
        alpn_str = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
        params.append(f"alpn={quote(alpn_str)}")
    
    if node.get('up') is not None:
        params.append(f"up={node['up']}")
    if node.get('down') is not None:
        params.append(f"down={node['down']}")

    if node.get('obfs') and node['obfs'] != 'none':
        params.append(f"obfs={quote(node['obfs'])}")
        if node.get('obfs-uri'):
            params.append(f"obfs-uri={quote(node['obfs-uri'])}")
    if node.get('fingerprint'):
        params.append(f"fp={quote(node['fingerprint'])}")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str
    
    remark = quote(node.get("name", "Hysteria_Node"))
    return f"hysteria://{node['server']}:{node['port']}{param_str}#{remark}"

def generate_tuic_link(node):
    params = []
    if node.get('tls'):
        params.append("tls=1")
    if node.get('servername'):
        params.append(f"sni={quote(node['servername'])}")
    if node.get('skip-cert-verify'):
        params.append("insecure=1")
    if node.get('congestion-controller'):
        params.append(f"cc={quote(node['congestion-controller'])}")
    if node.get('udp-relay-mode'):
        params.append(f"udp_relay_mode={quote(node['udp-relay-mode'])}")
    if node.get('disable-sni'):
        params.append("disable_sni=1")
    if node.get('alpn'):
        alpn_str = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
        params.append(f"alpn={quote(alpn_str)}")
    if node.get('fingerprint'):
        params.append(f"fingerprint={quote(node['fingerprint'])}")
    if node.get('flow'):
        params.append(f"flow={quote(node['flow'])}")
    if node.get('zero-rtt'):
        params.append("0-rtt=1")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str
    
    remark = quote(node.get("name", "TUIC_Node"))
    password = node.get('password', '')
    if not password and node.get('uuid'): # Fallback to UUID as password if password missing
        password = node['uuid']
    
    return f"tuic://{node['uuid']}:{password}@{node['server']}:{node['port']}{param_str}#{remark}"

def generate_vless_link(node):
    params = []
    if node.get('security'):
        params.append(f"security={quote(node['security'])}")
    if node.get('tls'):
        params.append("security=tls") # For VLESS, 'tls' is usually `security=tls`
    if node.get('servername'):
        params.append(f"sni={quote(node['servername'])}")
    if node.get('skip-cert-verify'):
        params.append("allowInsecure=1")
    if node.get('flow'):
        params.append(f"flow={quote(node['flow'])}")
    
    network_type = node.get('network', 'tcp')
    params.append(f"type={quote(network_type)}")

    if network_type == 'ws':
        params.append(f"path={quote(node.get('ws-path', '/'))}")
        if node.get('ws-headers') and node['ws-headers'].get('Host'):
            params.append(f"host={quote(node['ws-headers']['Host'])}")
    elif network_type == 'grpc':
        params.append(f"serviceName={quote(node.get('grpc-service-name', ''))}")
        if node.get('grpc-auto-commit'):
            params.append("grpcAutoCommit=1")
    
    if node.get('alpn'):
        alpn_str = ",".join(node["alpn"]) if isinstance(node["alpn"], list) else node["alpn"]
        params.append(f"alpn={quote(alpn_str)}")
    if node.get('fingerprint'):
        params.append(f"fp={quote(node['fingerprint'])}")
    
    if node.get('reality-opts') and node['reality-opts'].get('public-key'):
        params.append(f"pbk={quote(node['reality-opts']['public-key'])}")
        if node['reality-opts'].get('short-id'):
            params.append(f"sid={quote(node['reality-opts']['short-id'])}")
        if node['reality-opts'].get('spiderx'):
            params.append(f"spd={quote(node['reality-opts']['spiderx'])}")
            
    if node.get('xudp-opts') and node['xudp-opts'].get('udp-over-tcp'):
        params.append(f"udpotcp={quote(node['xudp-opts']['udp-over-tcp'])}")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str
    
    remark = quote(node.get("name", "VLESS_Node"))
    return f"vless://{node['uuid']}@{node['server']}:{node['port']}{param_str}#{remark}"

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

def main():
    start_total_time = time.time()
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    template_file_path = os.environ.get("CLASH_TEMPLATE_PATH", "clash_template.yml")
    geoip_db_path_env = os.environ.get("GEOIP_DB_PATH", "clash/Country.mmdb")

    init_geoip_reader(geoip_db_path_env)

    try:
        parts = url_list_repo_api.split('/')
        if len(parts) < 8 or parts[2] != 'api.github.com' or parts[3] != 'repos' or parts[6] != 'contents':
            raise ValueError("URL_LIST_REPO_API 看起来不是有效的 GitHub Content API URL。")
            
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except ValueError as ve:
        logger.critical(f"错误: {ve}")
        logger.critical("请确保 URL_LIST_REPO_API 正确设置为 GitHub Content API URL (例如：https://api.github.com/repos/user/repo/contents/path/to/file.txt)。")
        exit(1)
    except IndexError:
        logger.critical("错误: URL_LIST_REPO_API 格式不正确或不完整。无法提取所有者、仓库或文件路径。")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        logger.critical("错误: 环境变量 BOT 或 URL_LIST_REPO_API 未设置！")
        logger.critical("请确保您已在 GitHub Actions secrets/variables 中正确设置这些变量。")
        exit(1)

    logger.info("\n--- 正在从 GitHub 获取订阅 URL 列表 ---")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        logger.critical("无法获取 URL 列表或其 SHA，脚本终止。")
        exit(1)

    original_urls = set(url_content.strip().split('\n'))
    logger.info(f"从 GitHub 获取到 {len(original_urls)} 个订阅 URL。")

    enable_connectivity_test = os.environ.get("ENABLE_CONNECTIVITY_TEST", "true").lower() == "true"
    enable_china_filter = os.environ.get("EXCLUDE_CHINA_NODES", "false").lower() == "true"
    exclude_servers_str = os.environ.get("EXCLUDE_NODES_BY_SERVER", "")
    exclude_servers = [s.strip().lower() for s in exclude_servers_str.split(',') if s.strip()]

    all_raw_proxies, successful_urls_this_run = fetch_all_proxies_from_urls(list(original_urls))
    
    logger.info(f"\n--- 阶段 2/4: 进行节点去重 (初始 {len(all_raw_proxies)} 个代理) ---")
    unique_proxies_after_deduplication = {}
    for proxy_dict in all_raw_proxies:
        if proxy_dict:
            server_to_check = str(proxy_dict.get('server', '')).lower()
            if any(s in server_to_check for s in exclude_servers):
                logger.debug(f"  跳过代理 {proxy_dict.get('name', 'unknown')} (服务器: {server_to_check})，因为它在黑名单中。")
                continue
            
            fingerprint = generate_proxy_fingerprint(proxy_dict)
            if fingerprint not in unique_proxies_after_deduplication:
                unique_proxies_after_deduplication[fingerprint] = proxy_dict
            else:
                logger.debug(f"  发现重复节点，已跳过: {proxy_dict.get('name')} - {proxy_dict.get('server')}")
    
    proxies_after_deduplication = list(unique_proxies_after_deduplication.values())
    logger.info(f"--- 阶段 2/4 完成: 去重后得到 {len(proxies_after_deduplication)} 个唯一代理。 ---")

    logger.info(f"\n--- 阶段 3/4: 进行 GeoIP 中国节点过滤 (初始 {len(proxies_after_deduplication)} 个代理) ---")
    proxies_after_china_filter = []
    if enable_china_filter:
        for proxy_dict in proxies_after_deduplication:
            if not is_likely_china_node(proxy_dict):
                proxies_after_china_filter.append(proxy_dict)
            else:
                logger.debug(f"  节点 '{proxy_dict.get('name')}' 被识别为中国节点并已排除。")
        logger.info(f"--- 阶段 3/4 完成: 过滤中国节点后剩余 {len(proxies_after_china_filter)} 个代理。 ---")
    else:
        proxies_after_china_filter = proxies_after_deduplication
        logger.info("--- 阶段 3/4 完成: 中国节点过滤已禁用，跳过。 ---")

    final_filtered_proxies = []
    successful_proxy_count = 0
    total_proxies_for_test = len(proxies_after_china_filter)

    if enable_connectivity_test and total_proxies_for_test > 0:
        logger.info(f"\n--- 阶段 4/4: 开始并行连通性测试 (共 {total_proxies_for_test} 个代理) ---")
        max_workers = int(os.environ.get("MAX_WORKERS", 30))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(test_tcp_connectivity, p['server'], p['port']): p
                for p in proxies_after_china_filter if p.get('server') and isinstance(p.get('port'), int)
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
                        logger.debug(f"    节点 '{proxy_dict.get('name')}' ({server}:{port}) 连通性测试失败，已排除。")
                except Exception as exc:
                    logger.error(f"    连通性测试 {server}:{port} 时发生异常: {exc}")
                
                if processed_count % 50 == 0 or processed_count == total_proxies_for_test:
                    logger.info(f"    连通性测试进度: 已测试 {processed_count}/{total_proxies_for_test} 个代理...")

    else:
        logger.info("\n--- 阶段 4/4 完成: 连通性测试已禁用，跳过。 ---")
        for proxy_dict in proxies_after_china_filter:
            base_name = f"{proxy_dict.get('type', 'unknown').upper()}-{proxy_dict.get('server', 'unknown')}"
            proxy_dict['name'] = f"{base_name}-{generate_proxy_fingerprint(proxy_dict)[:8]}"
            final_filtered_proxies.append(proxy_dict)
            successful_proxy_count += 1

    logger.info(f"\n--- 所有阶段完成: 最终得到 {len(final_filtered_proxies)} 个有效代理节点。 ---")

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
    
    clash_config['proxies'] = final_filtered_proxies

    for group in clash_config.get('proxy-groups', []):
        if group.get('type') in ['select', 'url-test', 'fallback', 'loadbalance'] and 'proxies' in group:
            existing_special_proxies = [p for p in group['proxies'] if p in ["DIRECT", "自动选择", "GLOBAL"]]
            group['proxies'] = existing_special_proxies + [p['name'] for p in final_filtered_proxies]
            if group.get('type') in ['url-test', 'fallback']:
                group['proxies'] = list(dict.fromkeys(group['proxies']))

    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    clash_yaml_output_path = "clash.yaml"
    with open(clash_yaml_output_path, "w", encoding="utf-8") as f:
        f.write(final_clash_yaml)
    logger.info(f"Clash YAML 配置已成功写入 {clash_yaml_output_path}。")

    clash_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')
    with open("base64.txt", "w", encoding="utf-8") as f:
        f.write(clash_base64_encoded)
    logger.info("Base64 编码的 Clash YAML 配置已成功写入 base64.txt。")

    generic_links = []
    for node in final_filtered_proxies:
        node_type = node.get("type")
        link = None
        if node_type == "vmess":
            link = generate_vmess_link(node)
        elif node_type == "trojan":
            link = generate_trojan_link(node)
        elif node_type == "ss":
            link = generate_ss_link(node)
        elif node_type == "ssr":
            link = generate_ssr_link(node)
        elif node_type == "hysteria2":
            link = generate_hysteria2_link(node)
        elif node_type == "hysteria":
            link = generate_hysteria_link(node)
        elif node_type == "tuic":
            link = generate_tuic_link(node)
        elif node_type == "vless":
            link = generate_vless_link(node)
        
        if link:
            generic_links.append(link)

    combined_generic_links_str = "\n".join(generic_links)
    combined_generic_links_base64 = base64.b64encode(combined_generic_links_str.encode('utf-8')).decode('utf-8')

    general_links_output_path = "general_links.txt"
    with open(general_links_output_path, "w", encoding="utf-8") as f:
        f.write(combined_generic_links_base64)
    logger.info(f"通用客户端 Base64 订阅链接已成功写入 {general_links_output_path}。")

    end_total_time = time.time()
    logger.info(f"脚本总运行时间: {end_total_time - start_total_time:.2f} 秒。")

    print(f"::set-output name=total_proxies::{len(final_filtered_proxies)}")
    print(f"::set-output name=successful_proxies::{successful_proxy_count}")
    print(f"::set-output name=processed_urls::{len(successful_urls_this_run)}")

if __name__ == "__main__":
    main()
