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
import ipaddress # 用于 IP 地址验证
import maxminddb # 用于 GeoIP 查找

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%-Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# --- GeoIP 相关全局变量 ---
GEOIP_READER = None # 用于存储 maxminddb.Reader 对象
GEOIP_DB_PATH_GLOBAL = None # 用于存储 GeoIP 数据库路径

# --- GeoIP 初始化和查找函数 ---
def init_geoip_reader(db_path):
    """
    初始化 MaxMind GeoIP 数据库读取器。
    """
    global GEOIP_READER, GEOIP_DB_PATH_GLOBAL
    GEOIP_DB_PATH_GLOBAL = db_path
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
    """
    通过 GeoIP 数据库获取 IP 地址对应的国家代码。
    """
    if GEOIP_READER is None:
        return None
    try:
        match = GEOIP_READER.get(ip_address)
        if match and 'country' in match and 'iso_code' in match['country']:
            return match['country']['iso_code']
        # 有些数据库可能使用 registered_country
        if match and 'registered_country' in match and 'iso_code' in match['registered_country']:
            return match['registered_country']['iso_code']
    except Exception as e:
        logger.debug(f"GeoIP 查找 IP '{ip_address}' 失败: {e}")
    return None

# --- URL 验证函数 ---
def is_valid_url(url):
    """
    检查给定字符串是否是一个有效的 URL。
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# --- IP 地址验证函数 ---
def is_valid_ip(ip_str):
    """
    检查给定字符串是否是有效的 IP 地址。
    """
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

# --- 代理连通性测试函数 ---
def test_connectivity(proxy_url, test_url="https://www.google.com/generate_204", timeout=5):
    """
    测试代理的连通性。
    """
    try:
        # 使用 requests.Session 避免每次请求都创建新的连接池
        with requests.Session() as session:
            # 配置会话使用代理
            session.proxies = {'http': proxy_url, 'https': proxy_url}
            response = session.get(test_url, timeout=timeout)
            # 检查响应状态码，通常 204 表示成功无内容返回
            return response.status_code == 204
    except Exception as e:
        # 捕获所有请求异常 (连接错误、超时、DNS 解析失败等)
        # logger.debug(f"代理 '{proxy_url}' 连通性测试失败: {e}") # 调试信息，生产环境可关闭
        return False

# --- Base64 URL 安全解码函数 ---
def decode_base64_url(encoded_url):
    """
    解码 Base64 URL 安全字符串，处理填充问题。
    """
    try:
        # Base64 URL 安全编码可能缺少填充符，需要补齐
        missing_padding = len(encoded_url) % 4
        if missing_padding:
            encoded_url += '=' * (4 - missing_padding)
        decoded_bytes = base64.urlsafe_b64decode(encoded_url)
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        logger.debug(f"Base64 URL 解码失败: {encoded_url} - {e}")
        return None

# --- 代理字符串解析函数 (根据协议类型分发) ---
def parse_proxy_string(proxy_str):
    """
    根据代理字符串的协议头解析代理配置。
    """
    if not proxy_str:
        return None

    if proxy_str.startswith("ss://"):
        return parse_ss_proxy(proxy_str)
    elif proxy_str.startswith("vmess://"):
        return parse_vmess_proxy(proxy_str)
    elif proxy_str.startswith("trojan://"):
        return parse_trojan_proxy(proxy_str)
    elif proxy_str.startswith("ssr://"):
        return parse_ssr_proxy(proxy_str)
    elif proxy_str.startswith("hy2://"):
        return parse_hysteria2_proxy(proxy_str)
    elif proxy_str.startswith("vless://"):
        return parse_vless_proxy(proxy_str)
    elif proxy_str.startswith("warp://"):
        return parse_warp_proxy(proxy_str) # 预留 WARP 解析
    elif proxy_str.startswith("h1://"): # Hysteria V1
        return parse_hysteria_proxy(proxy_str)
    elif proxy_str.startswith("tuic://"):
        return parse_tuic_proxy(proxy_str)
    # 添加其他协议的解析...
    return None

# --- 各协议代理解析函数 ---
def parse_ss_proxy(ss_url):
    """
    解析 Shadowsocks (SS) 代理链接。
    """
    try:
        # SS 链接格式: ss://method:password@server:port#name 或 ss://base64(method:password@server:port)#name
        # 优先处理带有备注的部分
        if "#" in ss_url:
            parts = ss_url.split("#", 1)
            ss_url = parts[0]
            name = unquote(parts[1])
        else:
            # 如果没有备注，生成一个默认名称
            name = f"SS_Node_{hashlib.md5(ss_url.encode()).hexdigest()[:8]}"

        # 移除协议头
        scheme, rest = ss_url.split("://", 1)

        # 检查是否是 base64 编码的凭证部分
        if "@" in rest:
            creds, addr_port = rest.split("@", 1)
            # 凭证部分通常是 method:password 的 base64 编码
            method, password = base64.b64decode(creds).decode('utf-8').split(":", 1)
        else:
            # 如果没有 @，可能是旧版 ss://base64(method:password)/server:port 或 ss://base64(method:password@server:port)
            # 这里简化处理，假设为 ss://base64(method:password) 后直接跟 /server:port
            method_password_base64_decoded = base64.b64decode(rest).decode('utf-8')
            if "@" in method_password_base64_decoded: # 兼容 ss://base64(method:password@server:port)
                creds_decoded, addr_port = method_password_base64_decoded.split("@", 1)
                method, password = creds_decoded.split(":", 1)
            else: # ss://base64(method:password)/server:port 这种需要更复杂的正则，这里先简单按 : 处理
                method, password_and_addr = method_password_base64_decoded.split(":", 1)
                password, addr_port = password_and_addr.split("/", 1) # 假设 password 和 server:port 通过 / 分隔
            
        host, port_str = addr_port.split(":", 1)
        port = int(port_str)

        return {
            'name': name,
            'type': 'ss',
            'server': host,
            'port': port,
            'cipher': method,
            'password': password
        }
    except Exception as e:
        logger.debug(f"解析 SS 代理失败: {ss_url} - {e}")
        return None

def parse_vmess_proxy(vmess_url):
    """
    解析 VMess 代理链接。
    """
    try:
        # 移除协议头并进行 Base64 URL 安全解码
        decoded_str = decode_base64_url(vmess_url[len("vmess://"):])
        if not decoded_str:
            return None
        config = json.loads(decoded_str)

        # 提取 VMess 配置信息
        network = config.get('net', 'tcp') # 默认为 tcp
        tls_config = {}
        if config.get('tls') == 'tls':
            tls_config['tls'] = True
            if config.get('sni'):
                tls_config['servername'] = config['sni']
            if config.get('allowInsecure'):
                tls_config['skip-cert-verify'] = True

        ws_opts = {}
        if network == 'ws':
            ws_opts['path'] = config.get('path', '/')
            if config.get('host'):
                ws_opts['headers'] = {'Host': config['host']}
        
        # 兼容旧版 Vmess obfs 配置，在 Clash 中可能不再直接使用 'type' 作为 obfs 字段
        # 通常 VMess 的 obfs (mux, http, ws) 都由 network 和 ws-opts/grpc-opts 字段承载
        # 这里为了兼容性，如果 type 为 http/tls 且 network 不是 ws/grpc，则尝试映射为 Clash 的 obfs 字段
        obfs_type = config.get('type', '')
        obfs_params = {}
        if obfs_type == 'http':
            obfs_params['obfs'] = 'http'
            if config.get('host'):
                obfs_params['obfs-host'] = config['host']
            if config.get('path'):
                obfs_params['obfs-path'] = config['path'] # 某些情况下 http obfs 也会有 path
        elif obfs_type == 'tls':
            obfs_params['obfs'] = 'tls'
            if config.get('host'):
                obfs_params['obfs-host'] = config['host'] # 某些情况下 tls obfs 也会有 host

        proxy = {
            'name': config.get('ps', f"VMess_Node_{hashlib.md5(vmess_url.encode()).hexdigest()[:8]}"),
            'type': 'vmess',
            'server': config['add'],
            'port': int(config['port']),
            'uuid': config['id'],
            'alterId': int(config.get('aid', 0)),
            'cipher': config.get('scy', 'auto'), # stream security cipher, auto by default
            'network': network,
            'udp': True # 默认开启 UDP
        }
        if tls_config:
            proxy.update(tls_config)
        if ws_opts:
            proxy['ws-opts'] = ws_opts
        if obfs_params: # 仅在 network 不是 ws/grpc 时才考虑这些旧的 obfs 字段
            if network not in ['ws', 'grpc']:
                proxy.update(obfs_params)

        return proxy
    except Exception as e:
        logger.debug(f"解析 VMess 代理失败: {vmess_url} - {e}")
        return None

def parse_trojan_proxy(trojan_url):
    """
    解析 Trojan 代理链接。
    """
    try:
        parsed = urlparse(trojan_url)
        # 获取备注 (fragment)
        name = unquote(parsed.fragment) if parsed.fragment else f"Trojan_Node_{hashlib.md5(trojan_url.encode()).hexdigest()[:8]}"
        password = parsed.username
        host = parsed.hostname
        port = parsed.port

        query = parse_qs(parsed.query)
        # sni 字段，如果未指定则使用 hostname
        sni = query.get('sni', [host])[0]
        # skip-cert-verify
        skip_cert_verify = query.get('allowInsecure', ['0'])[0] == '1'
        udp = True # 默认开启 UDP

        proxy = {
            'name': name,
            'type': 'trojan',
            'server': host,
            'port': port,
            'password': password,
            'sni': sni,
            'skip-cert-verify': skip_cert_verify,
            'udp': udp
        }
        return proxy
    except Exception as e:
        logger.debug(f"解析 Trojan 代理失败: {trojan_url} - {e}")
        return None

def parse_ssr_proxy(ssr_url):
    """
    解析 ShadowsocksR (SSR) 代理链接。
    """
    try:
        # SSR 链接格式: ssr://base64_encoded_config
        encoded_part = ssr_url.split("ssr://")[1]
        # SSR 的 base64 编码可能没有填充符，需要手动补齐
        decoded_bytes = base64.urlsafe_b64decode(encoded_part + '=' * (4 - len(encoded_part) % 4))
        decoded_str = decoded_bytes.decode('utf-8')

        # SSR 配置字符串格式: server:port:protocol:method:obfs:password_base64/?params
        parts = decoded_str.split(":")
        if len(parts) < 6: # 至少包含 server, port, protocol, method, obfs, password
            logger.debug(f"SSR 链接格式不完整: {ssr_url}")
            return None

        server = parts[0]
        port = int(parts[1])
        protocol = parts[2]
        method = parts[3]
        obfs = parts[4]
        
        # 密码和参数部分
        password_base64_and_params = parts[5]

        # 密码部分是 base64 编码的，需要解码
        password_base64 = password_base64_and_params.split("/?")[0]
        password = base64.urlsafe_b64decode(password_base64 + '=' * (4 - len(password_base64) % 4)).decode('utf-8')

        params_str = ""
        if "/?" in password_base64_and_params:
            params_str = password_base64_and_params.split("/?")[1]
        
        # 解析参数
        params = parse_qs(params_str)

        # 备注 (remarks) 是 base64 编码的
        name_encoded = params.get('remarks', [f"SSR_Node_{hashlib.md5(ssr_url.encode()).hexdigest()[:8]}"])[0]
        name = unquote(base64.urlsafe_b64decode(name_encoded + '=' * (4 - len(name_encoded) % 4)).decode('utf-8'))
        
        # obfsparam 和 protoparam 也可能是 base64 编码的
        obfs_param = ""
        if 'obfsparam' in params:
            obfs_param_encoded = params['obfsparam'][0]
            obfs_param = unquote(base64.urlsafe_b64decode(obfs_param_encoded + '=' * (4 - len(obfs_param_encoded) % 4)).decode('utf-8'))
        
        protocol_param = ""
        if 'protoparam' in params:
            protocol_param_encoded = params['protoparam'][0]
            protocol_param = unquote(base64.urlsafe_b64decode(protocol_param_encoded + '=' * (4 - len(protocol_param_encoded) % 4)).decode('utf-8'))

        proxy = {
            'name': name,
            'type': 'ssr',
            'server': server,
            'port': port,
            'password': password,
            'cipher': method,
            'obfs': obfs,
            'protocol': protocol,
            'udp': True # 默认开启 UDP
        }
        if obfs_param:
            proxy['obfs-udp-header'] = obfs_param # Clash 中对应的字段
        if protocol_param:
            proxy['protocol-param'] = protocol_param

        return proxy
    except Exception as e:
        logger.debug(f"解析 SSR 代理失败: {ssr_url} - {e}")
        return None

def parse_hysteria2_proxy(hy2_url):
    """
    解析 Hysteria2 (hy2) 代理链接。
    """
    try:
        parsed_url = urlparse(hy2_url)
        password = parsed_url.username # Hysteria2 的 auth 通常在 username 部分
        host = parsed_url.hostname
        port = parsed_url.port
        name = unquote(parsed_url.fragment) if parsed_url.fragment else f"Hysteria2_Node_{hashlib.md5(hy2_url.encode()).hexdigest()[:8]}"

        query_params = parse_qs(parsed_url.query)
        sni = query_params.get('sni', [host])[0] # SNI 字段，默认为 host
        skip_cert_verify = query_params.get('insecure', ['0'])[0] == '1' # insecure 字段

        proxy = {
            'name': name,
            'type': 'hysteria2',
            'server': host,
            'port': port,
            'password': password, # Clash 中 Hysteria2 使用 password 字段
            'sni': sni,
            'skip-cert-verify': skip_cert_verify,
            'udp': True # 默认开启 UDP
        }
        return proxy
    except Exception as e:
        logger.debug(f"解析 Hysteria2 代理失败: {hy2_url} - {e}")
        return None

def parse_vless_proxy(vless_url):
    """
    解析 VLESS 代理链接。
    """
    try:
        parsed = urlparse(vless_url)
        name = unquote(parsed.fragment) if parsed.fragment else f"VLESS_Node_{hashlib.md5(vless_url.encode()).hexdigest()[:8]}"
        uuid = parsed.username
        host = parsed.hostname
        port = parsed.port

        query = parse_qs(parsed.query)

        transport_type = query.get('type', ['tcp'])[0] # 传输协议类型，默认为 tcp
        tls_enabled = 'tls' in query or 'xtls' in query # 是否启用 TLS/XTLS
        flow = query.get('flow', [None])[0] # 流控

        proxy = {
            'name': name,
            'type': 'vless',
            'server': host,
            'port': port,
            'uuid': uuid,
            'udp': True # 默认开启 UDP
        }

        if tls_enabled:
            proxy['tls'] = True
            if 'sni' in query:
                proxy['servername'] = query['sni'][0]
            if 'allowInsecure' in query and query['allowInsecure'][0] == '1':
                proxy['skip-cert-verify'] = True
            if 'fingerprint' in query: # TLS 指纹
                proxy['fingerprint'] = query['fingerprint'][0]
            if 'reality' in query and query['reality'][0] == '1': # Reality
                proxy['reality-opts'] = {
                    'public-key': query.get('pbk', [None])[0],
                    'short-id': query.get('sid', [None])[0]
                }

        if flow:
            proxy['flow'] = flow

        # 传输协议特定配置
        if transport_type == 'ws':
            proxy['network'] = 'ws'
            ws_opts = {}
            if 'path' in query:
                ws_opts['path'] = query['path'][0]
            if 'host' in query:
                ws_opts['headers'] = {'Host': query['host'][0]}
            if ws_opts:
                proxy['ws-opts'] = ws_opts
        elif transport_type == 'grpc':
            proxy['network'] = 'grpc'
            grpc_opts = {}
            if 'serviceName' in query:
                grpc_opts['service-name'] = query['serviceName'][0]
            if grpc_opts:
                proxy['grpc-opts'] = grpc_opts

        return proxy
    except Exception as e:
        logger.debug(f"解析 VLESS 代理失败: {vless_url} - {e}")
        return None

def parse_warp_proxy(warp_url):
    """
    解析 WARP 代理链接 (Clash 目前不支持直接的 WARP 代理类型，这里仅作占位符解析)。
    通常 WARP 在 Clash 中是通过集成 OpenClash 或使用特定的 tun 模式来间接实现的，
    而不是作为一个独立的proxy type。
    """
    try:
        parsed = urlparse(warp_url)
        name = unquote(parsed.fragment) if parsed.fragment else f"WARP_Node_{hashlib.md5(warp_url.encode()).hexdigest()[:8]}"
        
        # WARP 链接通常不包含服务器和端口，或者它们是 Cloudflare 的基础设施
        # 在 Clash 中，WARP通常通过特定的fake-ip或enhanced-mode来实现，而不是作为一个独立的proxy type
        # 这里仅作基本解析，可能需要进一步处理或整合到Clash的特定配置中
        
        return {
            'name': name,
            'type': 'http', # Placeholder, WARP is not a direct Clash proxy type
            'server': '127.0.0.1', # Placeholder
            'port': 0, # Placeholder
            'udp': True
        }
    except Exception as e:
        logger.debug(f"解析 WARP 代理失败: {warp_url} - {e}")
        return None

def parse_hysteria_proxy(h1_url):
    """
    解析 Hysteria (h1) 代理链接。
    """
    try:
        parsed_url = urlparse(h1_url)
        password = parsed_url.username # Hysteria V1 的 auth 通常在 username 部分
        host = parsed_url.hostname
        port = parsed_url.port
        name = unquote(parsed_url.fragment) if parsed_url.fragment else f"Hysteria_Node_{hashlib.md5(h1_url.encode()).hexdigest()[:8]}"

        query_params = parse_qs(parsed_url.query)
        sni = query_params.get('sni', [host])[0]
        alpn = query_params.get('alpn', ['h3'])[0] # 默认 alpn 为 h3
        insecure = query_params.get('insecure', ['0'])[0] == '1'
        
        # 带宽信息
        up_mbps = int(query_params.get('upmbps', [0])[0])
        down_mbps = int(query_params.get('downmbps', [0])[0])

        proxy = {
            'name': name,
            'type': 'hysteria',
            'server': host,
            'port': port,
            'auth': password, # Clash 中 Hysteria V1 使用 auth 字段
            'alpn': [alpn],
            'tls': True,
            'skip-cert-verify': insecure,
            'sni': sni,
            'udp': True # 默认开启 UDP
        }
        if up_mbps or down_mbps:
            proxy['bandwidth'] = {'up': f"{up_mbps}Mbps", 'down': f"{down_mbps}Mbps"}

        return proxy
    except Exception as e:
        logger.debug(f"解析 Hysteria 代理失败: {h1_url} - {e}")
        return None

def parse_tuic_proxy(tuic_url):
    """
    解析 TUIC 代理链接。
    """
    try:
        parsed_url = urlparse(tuic_url)
        password = parsed_url.username # TUIC 的密码通常在 username 部分
        host = parsed_url.hostname
        port = parsed_url.port
        name = unquote(parsed_url.fragment) if parsed_url.fragment else f"TUIC_Node_{hashlib.md5(tuic_url.encode()).hexdigest()[:8]}"

        query_params = parse_qs(parsed_url.query)
        sni = query_params.get('sni', [host])[0]
        insecure = query_params.get('insecure', ['0'])[0] == '1'
        alpn = query_params.get('alpn', ['h3'])[0] # 默认 alpn 为 h3
        congestion_controller = query_params.get('congestion_controller', ['bbr'])[0]
        udp_relay_mode = query_params.get('udp_relay_mode', ['native'])[0]

        proxy = {
            'name': name,
            'type': 'tuic',
            'server': host,
            'port': port,
            'password': password,
            'sni': sni,
            'skip-cert-verify': insecure,
            'alpn': [alpn],
            'congestion-controller': congestion_controller,
            'udp-relay-mode': udp_relay_mode,
            'udp': True # 默认开启 UDP
        }
        return proxy
    except Exception as e:
        logger.debug(f"解析 TUIC 代理失败: {tuic_url} - {e}")
        return None


# --- 获取和解析 URL 内容函数 ---
def fetch_and_parse_url(url_entry, session_timeout=15, enable_url_encoding_check=True):
    """
    从给定的 URL 获取订阅内容，并尝试解析出代理节点。
    支持 Clash YAML 格式和 Base64 编码的订阅。
    """
    url = url_entry.get('url')
    if not url:
        logger.warning(f"URL: '{url}' 解析失败或为空，可能没有获取到有效代理。") # 修正了打印 '' 的问题
        return None, url_entry

    # 检查并解码 URL 中的编码字符，这有助于处理一些不规范的订阅 URL
    if enable_url_encoding_check and "%" in url:
        try:
            decoded_url = unquote(url)
            if decoded_url != url:
                logger.debug(f"URL '{url}' 包含 URL 编码字符，已解码为 '{decoded_url}'。")
                url = decoded_url
        except Exception as e:
            logger.warning(f"URL 解码失败 '{url}': {e}")


    try:
        # 尝试获取 URL 内容
        response = requests.get(url, timeout=session_timeout)
        response.raise_for_status()  # 检查 HTTP 错误

        content = response.text
        if not content:
            logger.warning(f"URL: {url} 内容为空。")
            url_entry['fail_count'] += 1 # 失败计数加一
            return None, url_entry

        parsed_proxies = []

        # 尝试解析为 Clash YAML 格式
        try:
            clash_config = yaml.safe_load(content)
            if isinstance(clash_config, dict) and 'proxies' in clash_config and isinstance(clash_config['proxies'], list):
                # 提取 Clash 代理节点
                for proxy_dict in clash_config['proxies']:
                    if isinstance(proxy_dict, dict) and 'name' in proxy_dict: # 确保是字典且有name
                        parsed_proxies.append(proxy_dict)
                if parsed_proxies:
                    logger.info(f"URL: {url} 成功解析到 {len(parsed_proxies)} 个代理 (Clash YAML 格式)。")
                    url_entry['fail_count'] = 0 # 成功，重置失败计数
                    return parsed_proxies, url_entry
        except yaml.YAMLError:
            # 不是有效的 YAML，忽略并尝试下一种解析方式
            pass

        # 尝试解析为 Base64 编码的订阅链接列表
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            lines = decoded_content.splitlines()
            for line in lines:
                proxy = parse_proxy_string(line.strip())
                if proxy:
                    parsed_proxies.append(proxy)
            if parsed_proxies:
                logger.info(f"URL: {url} 成功解析到 {len(parsed_proxies)} 个代理 (Base64 编码)。")
                url_entry['fail_count'] = 0 # 成功，重置失败计数
                return parsed_proxies, url_entry
        except Exception:
            # 不是有效的 Base64 编码，忽略并尝试下一种解析方式
            pass

        # 尝试直接解析为文本行中的订阅链接
        lines = content.splitlines()
        for line in lines:
            proxy = parse_proxy_string(line.strip())
            if proxy:
                parsed_proxies.append(proxy)
        if parsed_proxies:
            logger.info(f"URL: {url} 成功解析到 {len(parsed_proxies)} 个代理 (文本行)。")
            url_entry['fail_count'] = 0 # 成功，重置失败计数
            return parsed_proxies, url_entry

        logger.warning(f"URL: {url} 内容未被识别为有效代理格式。")
        url_entry['fail_count'] += 1 # 失败计数加一
        return None, url_entry

    except requests.exceptions.RequestException as e:
        logger.error(f"获取 URL 失败: {url}，原因: {e}")
        url_entry['fail_count'] += 1 # 失败计数加一
        return None, url_entry
    except Exception as e:
        logger.error(f"处理 URL 时发生意外错误: {url}，原因: {e}")
        url_entry['fail_count'] += 1 # 失败计数加一
        return None, url_entry

# --- 生成唯一代理键函数 ---
def get_unique_proxy_key(proxy):
    """
    根据代理的类型和核心参数生成一个唯一的键，用于去重。
    """
    unique_parts = []
    # 根据不同代理类型选择不同的核心参数组合
    if proxy.get('type') == 'ss':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('cipher'), proxy.get('password')]
    elif proxy.get('type') == 'vmess':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('uuid')]
    elif proxy.get('type') == 'trojan':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('password'), proxy.get('sni')]
    elif proxy.get('type') == 'ssr':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('protocol'), proxy.get('cipher'), proxy.get('obfs'), proxy.get('password')]
    elif proxy.get('type') == 'hysteria2':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('password'), proxy.get('sni')]
    elif proxy.get('type') == 'vless':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('uuid'), proxy.get('tls')]
    elif proxy.get('type') == 'hysteria': # Hysteria V1
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('auth'), proxy.get('sni')]
    elif proxy.get('type') == 'tuic':
        unique_parts = [proxy.get('server'), proxy.get('port'), proxy.get('password'), proxy.get('sni')]
    elif proxy.get('type') == 'warp':
        unique_parts = [proxy.get('name')] # WARP 通常只有名称是唯一标识符
    
    # 将所有非 None 的部分拼接成字符串，然后计算 MD5 散列值
    key_string = '_'.join(str(p) for p in unique_parts if p is not None)
    return hashlib.md5(key_string.encode()).hexdigest()

# --- 过滤中国节点函数 ---
def filter_cn_nodes(proxies):
    """
    根据 GeoIP 数据库过滤掉中国的代理节点。
    """
    filtered_proxies = []
    if GEOIP_READER is None:
        logger.warning("GeoIP 数据库未加载，跳过中国节点过滤。")
        return proxies

    cn_ips_count = 0
    for proxy in proxies:
        server_ip = proxy.get('server')
        # 如果服务器地址不是有效的 IP，尝试进行 DNS 解析
        if not server_ip: # 有些节点可能没有server字段，或者为空
            filtered_proxies.append(proxy)
            continue
        
        try:
            if not is_valid_ip(server_ip):
                # logger.debug(f"解析 {server_ip} 的 IP 地址...")
                server_ip = socket.gethostbyname(server_ip) # 尝试解析域名
                # logger.debug(f"解析 {server_ip} 成功，IP 为 {server_ip}")
            
            country_code = get_country_code(server_ip)
            if country_code == 'CN':
                cn_ips_count += 1
            else:
                filtered_proxies.append(proxy)
        except (socket.gaierror, ValueError) as e:
            # DNS 解析失败或 IP 无效，无法判断国家，保留
            logger.warning(f"无法解析或验证 IP 地址 '{server_ip}' ({proxy.get('name', '未知节点')})，保留该节点。错误: {e}")
            filtered_proxies.append(proxy)
        except Exception as e:
            logger.warning(f"GeoIP 过滤时发生未知错误: {e}，保留节点 {proxy.get('name', '未知节点')}")
            filtered_proxies.append(proxy)
    logger.info(f"已识别出 {cn_ips_count} 个中国 IP 代理。")
    return filtered_proxies

# --- GitHub API 请求函数 ---
def github_api_request(url):
    """
    发送 HTTP GET 请求到 GitHub API。
    """
    headers = {'Accept': 'application/vnd.github.v3.raw'} # 请求原始文件内容
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # 对 4xx/5xx 错误抛出异常
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API 请求失败: {e}")
        return None

# --- 从 GitHub 获取文件内容函数 ---
def fetch_github_file(repo_owner, repo_name, file_path):
    """
    从 GitHub 仓库获取指定文件的内容。
    """
    github_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    logger.info(f"尝试从 GitHub API 获取文件: {github_url}")
    return github_api_request(github_url)

# --- 更新 GitHub 文件内容函数 ---
def update_github_file(repo_owner, repo_name, file_path, new_content, github_token, commit_message):
    """
    更新 GitHub 仓库中指定文件的内容。
    """
    github_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {
        'Authorization': f'token {github_token}',
        'Content-Type': 'application/json'
    }

    # 首先获取文件的当前 SHA
    try:
        response = requests.get(github_url, headers=headers, timeout=10)
        response.raise_for_status()
        file_data = response.json()
        sha = file_data['sha']
    except requests.exceptions.RequestException as e:
        logger.error(f"获取 {file_path} 当前 SHA 失败: {e}")
        return False

    # 准备更新请求的数据
    data = {
        'message': commit_message,
        'content': base64.b64encode(new_content.encode('utf-8')).decode('utf-8'), # 内容需要 Base64 编码
        'sha': sha # 必须提供当前 SHA
    }

    try:
        response = requests.put(github_url, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"更新 GitHub 文件 {file_path} 失败: {e}")
        if response.status_code == 409:
            logger.error("可能存在冲突，请检查仓库状态。")
        return False

# --- 生成通用订阅链接函数 ---
# 这些函数用于将解析到的代理配置重新转换为可用于其他客户端的订阅链接。
# 某些 Clash 特有字段可能无法完全映射。

def generate_vmess_link(node):
    """
    将 VMess 节点字典转换为 VMess 链接。
    """
    try:
        config = {
            "v": "2",
            "ps": node.get("name", ""),
            "add": node.get("server", ""),
            "port": node.get("port", 0),
            "id": node.get("uuid", ""),
            "aid": node.get("alterId", 0),
            "net": node.get("network", "tcp"),
            "type": node.get("type", "none"), # 用于兼容旧版 vm.json type 字段
            "host": node.get("ws-opts", {}).get("headers", {}).get("Host", ""),
            "path": node.get("ws-opts", {}).get("path", "/"),
            "tls": "tls" if node.get("tls") else "",
            "sni": node.get("servername", ""),
            "scy": node.get("cipher", "auto") # Stream Security Cipher
        }
        # 移除空值字段以保持链接简洁
        config_cleaned = {k: v for k, v in config.items() if v not in ["", 0, None, {}]}
        return "vmess://" + base64.b64encode(json.dumps(config_cleaned, ensure_ascii=False).encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"生成 VMess 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_trojan_link(node):
    """
    将 Trojan 节点字典转换为 Trojan 链接。
    """
    try:
        params = []
        if node.get('sni'):
            params.append(f"sni={node['sni']}")
        if node.get('skip-cert-verify'):
            params.append("allowInsecure=1") # Trojan 链接使用 allowInsecure
        
        query_string = "?" + "&".join(params) if params else ""
        # 节点名称需要进行 URL 编码
        return f"trojan://{node.get('password')}@{node.get('server')}:{node.get('port')}{query_string}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 Trojan 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_ss_link(node):
    """
    将 SS 节点字典转换为 SS 链接。
    """
    try:
        # SS 凭证部分是 method:password 的 base64 编码
        creds = base64.b64encode(f"{node.get('cipher')}:{node.get('password')}".encode()).decode()
        # 节点名称需要进行 URL 编码
        return f"ss://{creds}@{node.get('server')}:{node.get('port')}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 SS 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_ssr_link(node):
    """
    将 SSR 节点字典转换为 SSR 链接。
    """
    try:
        # SSR 密码和备注需要 Base64 URL 安全编码
        password_b64 = base64.urlsafe_b64encode(node.get('password', '').encode()).decode().rstrip('=')
        remarks_b64 = base64.urlsafe_b64encode(node.get('name', '').encode()).decode().rstrip('=')
        
        params = []
        params.append(f"remarks={remarks_b64}")
        if node.get('obfs-udp-header'): # obfsparam
            params.append(f"obfsparam={base64.urlsafe_b64encode(node['obfs-udp-header'].encode()).decode().rstrip('=')}")
        if node.get('protocol-param'): # protoparam
            params.append(f"protoparam={base64.urlsafe_b64encode(node['protocol-param'].encode()).decode().rstrip('=')}")
        
        param_string = "&".join(params)
        
        # 拼接 SSR URI 的核心部分
        encoded_uri = f"{node.get('server')}:{node.get('port')}:{node.get('protocol')}:{node.get('cipher')}:{node.get('obfs')}:{password_b64}/?{param_string}"
        # 整个 URI 再进行 Base64 URL 安全编码
        return "ssr://" + base64.urlsafe_b64encode(encoded_uri.encode()).decode().rstrip('=')
    except Exception as e:
        logger.error(f"生成 SSR 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_hysteria2_link(node):
    """
    将 Hysteria2 节点字典转换为 Hysteria2 链接。
    """
    try:
        params = []
        if node.get('sni'):
            params.append(f"sni={node['sni']}")
        if node.get('skip-cert-verify'):
            params.append("insecure=1") # Hysteria2 链接使用 insecure
        
        query_string = "?" + "&".join(params) if params else ""
        return f"hy2://{node.get('password')}@{node.get('server')}:{node.get('port')}{query_string}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 Hysteria2 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_hysteria_link(node):
    """
    将 Hysteria (h1) 节点字典转换为 Hysteria (h1) 链接。
    """
    try:
        params = []
        if node.get('sni'):
            params.append(f"sni={node['sni']}")
        if node.get('alpn') and isinstance(node['alpn'], list):
            params.append(f"alpn={node['alpn'][0]}")
        if node.get('skip-cert-verify'):
            params.append("insecure=1")
        if node.get('bandwidth'):
            if 'up' in node['bandwidth'] and isinstance(node['bandwidth']['up'], str):
                # 提取数字部分
                up_mbps = int(re.search(r'(\d+)', node['bandwidth']['up']).group(1))
                params.append(f"upmbps={up_mbps}")
            if 'down' in node['bandwidth'] and isinstance(node['bandwidth']['down'], str):
                down_mbps = int(re.search(r'(\d+)', node['bandwidth']['down']).group(1))
                params.append(f"downmbps={down_mbps}")

        query_string = "?" + "&".join(params) if params else ""
        return f"h1://{node.get('auth')}@{node.get('server')}:{node.get('port')}{query_string}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 Hysteria 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_tuic_link(node):
    """
    将 TUIC 节点字典转换为 TUIC 链接。
    """
    try:
        params = []
        if node.get('sni'):
            params.append(f"sni={node['sni']}")
        if node.get('skip-cert-verify'):
            params.append("insecure=1")
        if node.get('alpn') and isinstance(node['alpn'], list):
            params.append(f"alpn={node['alpn'][0]}")
        if node.get('congestion-controller'):
            params.append(f"congestion_controller={node['congestion-controller']}")
        if node.get('udp-relay-mode'):
            params.append(f"udp_relay_mode={node['udp-relay-mode']}")
        
        query_string = "?" + "&".join(params) if params else ""
        return f"tuic://{node.get('password')}@{node.get('server')}:{node.get('port')}{query_string}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 TUIC 链接失败: {node.get('name', '未知')} - {e}")
        return None

def generate_vless_link(node):
    """
    将 VLESS 节点字典转换为 VLESS 链接。
    """
    try:
        params = []
        params.append(f"type={node.get('network', 'tcp')}") # 传输协议类型

        if node.get('tls'):
            params.append("security=tls") # 启用 TLS
            if node.get('servername'):
                params.append(f"sni={node['servername']}")
            if node.get('skip-cert-verify'):
                params.append("allowInsecure=1") # VLESS 链接使用 allowInsecure
            if node.get('fingerprint'):
                params.append(f"fp={node['fingerprint']}") # TLS 指纹
            if node.get('reality-opts'): # Reality 协议
                if node['reality-opts'].get('public-key'):
                    params.append(f"pbk={node['reality-opts']['public-key']}")
                if node['reality-opts'].get('short-id'):
                    params.append(f"sid={node['reality-opts']['short-id']}")
        
        if node.get('flow'): # 流控
            params.append(f"flow={node['flow']}")
        
        # 传输协议特定参数
        if node.get('network') == 'ws' and node.get('ws-opts'):
            if node['ws-opts'].get('path'):
                params.append(f"path={node['ws-opts']['path']}")
            if node['ws-opts'].get('headers', {}).get('Host'):
                params.append(f"host={node['ws-opts']['headers']['Host']}")
        elif node.get('network') == 'grpc' and node.get('grpc-opts'):
            if node['grpc-opts'].get('service-name'):
                params.append(f"serviceName={node['grpc-opts']['service-name']}")

        query_string = "?" + "&".join(params) if params else ""
        return f"vless://{node.get('uuid')}@{node.get('server')}:{node.get('port')}{query_string}#{quote(node.get('name', ''))}"
    except Exception as e:
        logger.error(f"生成 VLESS 链接失败: {node.get('name', '未知')} - {e}")
        return None


# --- 主函数 ---
def main():
    start_total_time = time.time()

    # --- 从环境变量获取配置参数 ---
    # 这些环境变量需要在 GitHub Actions 或本地环境中设置
    github_repo_owner = os.environ.get('GITHUB_REPO_OWNER')
    github_repo_name = os.environ.get('GITHUB_REPO_NAME')
    github_token = os.environ.get('GITHUB_TOKEN') # 用于 GitHub API 认证

    # 文件路径和输出设置
    subscribe_url_file = os.environ.get('SUBSCRIBE_URL_FILE', 'data/url.txt') # 订阅 URL 列表文件
    clash_template_file = os.environ.get('CLASH_TEMPLATE_FILE', 'clash_template.yml') # Clash 配置模板文件
    output_base64_file = os.environ.get('OUTPUT_BASE64_FILE', 'clash_base64.txt') # 输出 Base64 编码的 Clash 配置
    output_clash_yaml_file = os.environ.get('OUTPUT_CLASH_YAML_FILE', 'clash_config.yaml') # 输出原始 Clash YAML 配置
    general_links_output_path = os.environ.get('GENERAL_LINKS_OUTPUT_PATH', 'general_links.txt') # 输出通用客户端订阅链接
    
    # 其他配置
    max_fail_count = int(os.environ.get('MAX_FAIL_COUNT', 5)) # URL 最大失败次数
    concurrency_limit = int(os.environ.get('CONCURRENCY_LIMIT', 10)) # 并发处理的 URL 数量
    test_timeout = int(os.environ.get('TEST_TIMEOUT', 5)) # 连通性测试超时时间
    geoip_db_path = os.environ.get('GEOIP_DB_PATH', 'clash/Country.mmdb') # GeoIP 数据库路径

    # 检查必要的环境变量是否设置
    if not all([github_repo_owner, github_repo_name, github_token]):
        logger.critical("缺少 GitHub 仓库所有者、仓库名称或 TOKEN 环境变量。请检查配置。")
        exit(1) # 如果缺少必要参数，则退出

    # 初始化 GeoIP 读取器
    init_geoip_reader(geoip_db_path)

    initial_url_entries = []
    failed_urls_file = 'failed_urls.json'

    # 加载上次运行失败的 URL 列表
    if os.path.exists(failed_urls_file):
        try:
            with open(failed_urls_file, 'r', encoding='utf-8') as f:
                initial_url_entries = json.load(f)
            logger.info(f"已加载 {len(initial_url_entries)} 个上次失败的 URL。")
        except json.JSONDecodeError:
            logger.warning("无法解析 failed_urls.json，将重新获取所有 URL。")
            initial_url_entries = []

    # --- 阶段 1: 获取订阅 URL 列表 ---
    logger.info("\n--- 正在从 GitHub 获取订阅 URL 列表 ---")
    github_urls_content = fetch_github_file(github_repo_owner, github_repo_name, subscribe_url_file)

    github_url_map = {} # 用于存储所有 URL 及其失败计数
    if github_urls_content:
        lines = github_urls_content.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and is_valid_url(line):
                github_url_map[line] = {'url': line, 'fail_count': 0} # 初始失败计数为 0
        logger.info(f"从 GitHub 获取到 {len(github_url_map)} 个订阅 URL。")
    else:
        logger.critical("无法从 GitHub 获取订阅 URL 列表，程序退出。请检查 GitHub 仓库配置和网络连接。")
        exit(1)

    # 合并上次的失败计数
    for entry in initial_url_entries:
        url = entry.get('url')
        if url and url in github_url_map:
            github_url_map[url]['fail_count'] = entry.get('fail_count', 0)

    # 划分活动 URL 和失效 URL
    active_url_entries = [
        entry for entry in github_url_map.values()
        if entry['fail_count'] < max_fail_count
    ]
    stale_url_entries = [
        entry for entry in github_url_map.values()
        if entry['fail_count'] >= max_fail_count
    ]
    if stale_url_entries:
        for entry in stale_url_entries:
            logger.warning(f"URL '{entry['url']}' 失败次数已达 {entry['fail_count']} 次，将不再尝试获取。")

    logger.info(f"\n--- 阶段 1/4: 并行下载和解析订阅 (最大 {concurrency_limit} 个并发) ---")
    all_parsed_proxies_raw = []
    updated_url_entries = [] # 用于保存更新后的 URL 状态

    # 使用线程池并行下载和解析 URL
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_limit) as executor:
        futures = {executor.submit(fetch_and_parse_url, entry): entry for entry in active_url_entries}
        for future in concurrent.futures.as_completed(futures):
            parsed_result, original_entry = future.result()
            if parsed_result:
                all_parsed_proxies_raw.extend(parsed_result)
            updated_url_entries.append(original_entry)
            
    # 保存更新后的失败 URL 列表
    all_url_entries_for_save = updated_url_entries + stale_url_entries # 确保所有 URL 都被保存，包括已失效的
    with open(failed_urls_file, 'w', encoding='utf-8') as f:
        json.dump(all_url_entries_for_save, f, ensure_ascii=False, indent=2)
    logger.info(f"更新后的失败 URL 跟踪记录已保存到 {failed_urls_file}。")

    logger.info(f"--- 阶段 1/4 完成: 成功从 {len([u for u in updated_url_entries if u['fail_count'] == 0])} 个 URL 获取到 {len(all_parsed_proxies_raw)} 个原始代理。 ---")


    # --- 阶段 2: 节点去重 ---
    logger.info("\n--- 阶段 2/4: 进行节点去重 (初始 %d 个代理) ---" % len(all_parsed_proxies_raw))
    unique_proxies_map = {}
    for proxy in all_parsed_proxies_raw:
        key = get_unique_proxy_key(proxy)
        if key not in unique_proxies_map:
            unique_proxies_map[key] = proxy
    all_parsed_proxies = list(unique_proxies_map.values())
    logger.info(f"--- 阶段 2/4 完成: 去重后得到 {len(all_parsed_proxies)} 个唯一代理。 ---")

    # --- 阶段 3: GeoIP 中国节点过滤 ---
    logger.info(f"\n--- 阶段 3/4: 进行 GeoIP 中国节点过滤 (初始 {len(all_parsed_proxies)} 个代理) ---")
    filtered_proxies = filter_cn_nodes(all_parsed_proxies)
    logger.info(f"--- 阶段 3/4 完成: 过滤中国节点后剩余 {len(filtered_proxies)} 个代理。 ---")

    all_parsed_proxies = filtered_proxies # 更新为过滤后的代理列表


    # --- 阶段 4: 并行连通性测试 ---
    logger.info(f"\n--- 阶段 4/4: 开始并行连通性测试 (共 {len(all_parsed_proxies)} 个代理) ---")
    valid_proxies = []
    test_proxies_with_url = [] # 存储 (代理链接, 代理对象) 元组，用于测试

    for p in all_parsed_proxies:
        link_to_test = None
        # 根据代理类型生成相应的链接，用于连通性测试
        if p.get('type') == 'ss':
            link_to_test = generate_ss_link(p)
        elif p.get('type') == 'vmess':
            link_to_test = generate_vmess_link(p)
        elif p.get('type') == 'trojan':
            link_to_test = generate_trojan_link(p)
        elif p.get('type') == 'vless':
            link_to_test = generate_vless_link(p)
        elif p.get('type') == 'hysteria2':
             link_to_test = generate_hysteria2_link(p)
        elif p.get('type') == 'ssr':
            link_to_test = generate_ssr_link(p)
        elif p.get('type') == 'hysteria':
            link_to_test = generate_hysteria_link(p)
        elif p.get('type') == 'tuic':
            link_to_test = generate_tuic_link(p)
        # WARP 节点因为其特殊性，不适合直接用代理链接测试，通常不加入此循环
        # elif p.get('type') == 'warp':
        #    link_to_test = generate_warp_link(p) # 如果有 WARP 链接生成函数

        if link_to_test:
            test_proxies_with_url.append((link_to_test, p))
        else:
            logger.warning(f"不支持的代理类型或链接生成失败，跳过连通性测试: {p.get('type')} - {p.get('name', '未知')}")


    if not test_proxies_with_url:
        logger.warning("没有可用于测试的代理节点。")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_limit) as executor:
            # 提交任务，并关联代理对象
            future_to_proxy = {executor.submit(test_connectivity, proxy_url, timeout=test_timeout): proxy_obj for proxy_url, proxy_obj in test_proxies_with_url if proxy_url is not None}
            
            processed_count = 0
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy_obj = future_to_proxy[future] # 获取对应的代理对象
                processed_count += 1
                # 打印进度
                if processed_count % 50 == 0 or processed_count == len(future_to_proxy):
                    logger.info(f"    连通性测试进度: 已测试 {processed_count}/{len(future_to_proxy)} 个代理...")
                try:
                    is_valid = future.result()
                    if is_valid:
                        valid_proxies.append(proxy_obj)
                except Exception as exc:
                    logger.debug(f"代理 '{proxy_obj.get('name', '未知')}' 连通性测试异常: {exc}") # 打印测试失败的详细原因

    all_parsed_proxies = valid_proxies # 最终的有效代理列表
    logger.info(f"\n--- 所有阶段完成: 最终得到 {len(all_parsed_proxies)} 个有效代理节点。 ---")

    # --- 更新 GitHub URL 列表文件 ---
    # 重新构建新的 URL 列表内容，只包含未达到最大失败次数的 URL
    new_github_urls_content = ""
    for entry in all_url_entries_for_save:
        new_github_urls_content += entry['url'] + "\n"
    
    # 写入 GitHub
    logger.info("正在更新 GitHub url.txt 文件...")
    # 检查文件内容是否实际有变化，避免不必要的 commit
    current_github_urls_content = fetch_github_file(github_repo_owner, github_repo_name, subscribe_url_file)
    if current_github_urls_content and current_github_urls_content.strip() == new_github_urls_content.strip():
        logger.info("url.txt 文件内容未更改，无需更新。")
    else:
        if update_github_file(github_repo_owner, github_repo_name, subscribe_url_file, new_github_urls_content, github_token, "Update subscribe URLs"):
            logger.info("成功更新 GitHub 上的 data/url.txt。")
        else:
            logger.error("更新 GitHub 上的 data/url.txt 失败。")


    # --- 生成 Clash 配置 ---
    try:
        with open(clash_template_file, 'r', encoding='utf-8') as f:
            clash_config = yaml.safe_load(f)
        logger.info(f"已从 {clash_template_file} 加载 Clash 配置模板。")
    except FileNotFoundError:
        logger.critical(f"未找到 Clash 模板文件 '{clash_template_file}'！请创建它。")
        exit(1)
    except yaml.YAMLError as e:
        logger.critical(f"解析 Clash 模板文件 '{clash_template_file}' 时出错: {e}")
        exit(1)
    
    # 将获取到的所有有效代理节点添加到 Clash 配置的 'proxies' 部分
    clash_config['proxies'] = all_parsed_proxies

    # 根据 Clash 配置中的 proxy-groups 动态添加节点
    proxy_names = [p['name'] for p in all_parsed_proxies]
    for group in clash_config.get('proxy-groups', []):
        # 确保 group['proxies'] 是一个列表，如果为 None 则初始化为空列表
        current_proxies = group.get('proxies')
        if current_proxies is None:
            current_proxies = []
        elif not isinstance(current_proxies, list):
            # 如果不是列表，强制转换为列表以避免 TypeError，例如模板中只有一个字符串
            current_proxies = [current_proxies]

        # 找出当前组中保留的特殊代理（如 DIRECT, 自动选择, GLOBAL）
        existing_special_proxies = [p for p in current_proxies if p in ["DIRECT", "自动选择", "GLOBAL"]]

        # 假设你的节点选择组叫 '🚀 节点选择' 和 '🔰 Fallback'
        if group['name'] == '🚀 节点选择':
            new_proxies = []
            # 确保 DIRECT 只添加一次，并且放在最前面
            if "DIRECT" not in existing_special_proxies:
                new_proxies.append("DIRECT")
            new_proxies.extend(proxy_names) # 添加所有获取到的代理名称
            group['proxies'] = new_proxies
        elif group['name'] == '🔰 Fallback':
            new_proxies = []
            new_proxies.extend(proxy_names) # Fallback 组通常只包含代理节点
            group['proxies'] = new_proxies
        # 你可以根据你的模板文件中的实际组名称进行调整
    
    # 将更新后的 Clash 配置转换为 YAML 格式
    final_clash_yaml = yaml.dump(clash_config, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)

    # 将 YAML 配置进行 Base64 编码
    final_base64_encoded = base64.b64encode(final_clash_yaml.encode('utf-8')).decode('utf-8')

    # 保存 Base64 编码的 Clash 配置
    with open(output_base64_file, 'w', encoding='utf-8') as f:
        f.write(final_base64_encoded)
    logger.info(f"Base64 编码的 Clash 配置已保存到 {output_base64_file}。")

    # 保存原始 Clash YAML 配置
    with open(output_clash_yaml_file, 'w', encoding='utf-8') as f:
        f.write(final_clash_yaml)
    logger.info(f"原始 Clash YAML 配置已保存到 {output_clash_yaml_file}。")

    # --- 生成通用订阅链接 ---
    generic_links = []
    for node in all_parsed_proxies:
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
        elif node_type == "hysteria": # Hysteria V1
            link = generate_hysteria_link(node)
        elif node_type == "tuic":
            link = generate_tuic_link(node)
        elif node_type == "vless":
            link = generate_vless_link(node)
        # WARP 链接通常不直接生成在这里，因为它不是主流代理协议
        
        if link:
            generic_links.append(link)

    # 将所有通用链接合并并 Base64 编码
    combined_generic_links_str = "\n".join(generic_links)
    combined_generic_links_base64 = base64.b64encode(combined_generic_links_str.encode('utf-8')).decode('utf-8')

    # 保存通用客户端订阅链接
    with open(general_links_output_path, "w", encoding="utf-8") as f:
        f.write(combined_generic_links_base64)
    logger.info(f"通用客户端 Base64 订阅链接已成功写入 {general_links_output_path}。")

    end_total_time = time.time()
    logger.info(f"脚本总运行时间: {end_total_time - start_total_time:.2f} 秒。")

if __name__ == '__main__':
    main()
