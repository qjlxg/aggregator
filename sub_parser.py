import os, requests, base64, re, socket, maxminddb, concurrent.futures, json, yaml, hashlib, time, logging
from urllib.parse import urlparse, unquote, parse_qs

# 配置日志（可选，用于调试）
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_flag(code):
    if not code: return "🌐"
    try:
        return "".join(chr(127397 + ord(c)) for c in code.upper())
    except:
        return "🌐"

def decode_base64(data):
    if not data: return ""
    try:
        data = data.replace("-", "+").replace("_", "/")
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data.strip())
        missing_padding = len(clean_data) % 4
        if missing_padding: clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except Exception as e:
        logger.debug(f"Base64 decode failed: {e}")
        return ""

def get_ip(hostname):
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return None

def get_short_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:4]

def parse_usage_and_expire(content, headers):
    """解析订阅响应头中的流量和过期信息"""
    info = {"upload": 0, "download": 0, "total": 0, "expire": 0}
    user_info = headers.get('Subscription-Userinfo') or headers.get('subscription-userinfo', '')
    if user_info:
        parts = user_info.split(';')
        for part in parts:
            if '=' in part:
                try:
                    k, v = part.strip().split('=', 1)
                    if v.isdigit(): info[k.lower()] = int(v)
                except ValueError:
                    continue
    return info

def parse_uri_to_clash(uri):
    """增强版：支持 SS/SSR, VMess, VLESS, Trojan, Hy2, TUIC, Socks5。更多参数支持，异常细化"""
    try:
        if "://" not in uri: return None
        parts = uri.split('#', 1)
        base_uri = parts[0]
        tag = unquote(parts[1]) if len(parts) > 1 else "Node"
        parsed = urlparse(base_uri)
        if not parsed.hostname: return None
        node = {
            "name": tag,
            "server": parsed.hostname,
            "port": int(parsed.port or 443),
            "udp": True
        }
        # 统一解析 query 参数
        query = parse_qs(parsed.query) if parsed.query else {}
        query_lower = {k.lower(): v[0] if v else '' for k, v in query.items()}

        scheme = parsed.scheme.lower()

        if scheme == 'ss':
            # SS: ss://base64(method:password)@host:port?params#tag
            try:
                auth_b64 = parsed.netloc.split('@')[0]
                auth = decode_base64(auth_b64)
                if ':' in auth:
                    method, password = auth.split(':', 1)
                    node.update({"type": "ss", "cipher": method, "password": password})
                    # SS params: plugin, plugin-opts 等（简化）
                    if 'plugin' in query_lower:
                        node['plugin'] = query_lower['plugin']
                        node['plugin-opts'] = query_lower.get('pluginopts', '')
                    return node
            except Exception as e:
                logger.debug(f"SS parse failed: {e}")
                return None

        elif scheme == 'ssr':
            # SSR: ssr://base64(method:password:protocol:protocol_param:obfs:obfs_param:host:port)
            try:
                ssr_b64 = base_uri.replace("ssr://", "")
                ssr_decoded = decode_base64(ssr_b64)
                if ':' not in ssr_decoded: return None
                parts = ssr_decoded.rsplit(':', 2)  # host:port 在最后
                params_str = ':'.join(parts[:-2])
                host_port = parts[-2] + ':' + parts[-1]
                params = params_str.split(':')
                if len(params) >= 6:
                    method, pwd, proto, proto_param, obfs, obfs_param = params[:6]
                    node.update({
                        "type": "ssr",
                        "cipher": method,
                        "password": decode_base64(pwd) if pwd else '',
                        "protocol": proto,
                        "protocol-param": decode_base64(proto_param) if proto_param else '',
                        "obfs": obfs,
                        "obfs-param": decode_base64(obfs_param) if obfs_param else ''
                    })
                    host_port_parsed = urlparse(f"ssr://{host_port}")
                    node["server"] = host_port_parsed.hostname
                    node["port"] = int(host_port_parsed.port or 443)
                    return node
            except Exception as e:
                logger.debug(f"SSR parse failed: {e}")
                return None

        elif scheme == 'vmess':
            # VMess: vmess://base64(JSON)
            try:
                v2_json = decode_base64(base_uri[8:])  # remove vmess://
                v2 = json.loads(v2_json)
                node.update({
                    "type": "vmess",
                    "uuid": v2.get('id'),
                    "alterId": int(v2.get('aid', 0)),
                    "cipher": v2.get('cy', 'auto'),
                    "tls": v2.get('tls') in ["tls", True],
                    "network": v2.get('net', 'tcp')
                })
                network = node["network"]
                if network == 'ws':
                    node["ws-opts"] = {
                        "path": v2.get('path', '/'),
                        "headers": {"Host": v2.get('host', '')}
                    }
                elif network == 'grpc':
                    node["grpc-opts"] = {
                        "grpc-service-name": v2.get('path', ''),
                        "host": v2.get('host', '')
                    }
                # SNI 等
                if node["tls"]:
                    node["servername"] = v2.get('sni', v2.get('host', ''))
                return node
            except Exception as e:
                logger.debug(f"VMess parse failed: {e}")
                return None

        elif scheme == 'vless':
            node.update({
                "type": "vless",
                "uuid": parsed.username or '',
                "flow": query_lower.get('flow', ''),
                "network": query_lower.get('type', 'tcp'),
                "servername": query_lower.get('sni', ''),
                "tls": query_lower.get('security', '') in ['tls', 'reality']
            })
            network = node["network"]
            if network == 'ws':
                node["ws-opts"] = {
                    "path": query_lower.get('path', '/'),
                    "headers": {"Host": query_lower.get('host', '')}
                }
            elif network == 'grpc':
                node["grpc-opts"] = {
                    "grpc-service-name": query_lower.get('serviceName', ''),
                    "host": query_lower.get('host', '')
                }
            if query_lower.get('security') == 'reality':
                node["reality-opts"] = {
                    "public-key": query_lower.get('pbk', ''),
                    "short-id": query_lower.get('sid', '')
                }
            return node

        elif scheme in ['hysteria2', 'hy2']:
            node.update({
                "type": "hysteria2",
                "password": parsed.username or query_lower.get('auth', ''),
                "sni": query_lower.get('sni', ''),
                "skip-cert-verify": query_lower.get('insecure', '0') == '1'
            })
            # 支持 up/down 等（Clash Hysteria2 支持）
            if 'up' in query_lower: node['up'] = query_lower['up'] + ' mbps'
            if 'down' in query_lower: node['down'] = query_lower['down'] + ' mbps'
            return node

        elif scheme == 'trojan':
            node.update({
                "type": "trojan",
                "password": parsed.username or '',
                "sni": query_lower.get('sni', ''),
                "skip-cert-verify": query_lower.get('insecure', '0') == '1'
            })
            network = query_lower.get('type', 'tcp')
            if network == 'ws':
                node["ws-opts"] = {
                    "path": query_lower.get('path', '/'),
                    "headers": {"Host": query_lower.get('host', '')}
                }
            return node

        elif scheme == 'tuic':
            node.update({
                "type": "tuic",
                "uuid": parsed.username or query_lower.get('token', ''),
                "cipher": query_lower.get('cipher', 'none'),
                "sni": query_lower.get('sni', ''),
                "skip-cert-verify": query_lower.get('insecure', '0') == '1'
            })
            if 'udp-relay-mode' in query_lower:
                node['udp-relay-mode'] = query_lower['udp-relay-mode']
            if 'congestion-controller' in query_lower:
                node['congestion-controller'] = query_lower['congestion-controller']
            return node

        elif scheme in ['socks5', 'socks']:
            node.update({
                "type": "socks5",
                "username": parsed.username.split(':')[0] if parsed.username else '',
                "password": parsed.password if parsed.password else ''
            })
            return node

        else:
            logger.debug(f"Unsupported scheme: {scheme}")
            return None

    except Exception as e:
        logger.debug(f"Parse URI failed for {uri[:50]}...: {e}")
        return None

def rename_node(uri, reader):
    """强制清洗备注：仅保留 [国旗] [国家名] [唯一ID]"""
    try:
        base_uri = uri.split('#')[0]
        parsed = urlparse(base_uri)
        ip = get_ip(parsed.hostname)
        country_name, flag = "未知地区", "🌐"
        
        if ip and reader:
            match = reader.get(ip)
            if match and match.get('country'):
                names = match['country'].get('names', {})
                zh_name = names.get('zh-CN')
                if zh_name:
                    country_name = zh_name
                iso_code = match['country'].get('iso_code')
                if iso_code:
                    flag = get_flag(iso_code)

        new_tag = f"{flag} {country_name} {get_short_id(base_uri)}"
        return f"{base_uri}#{new_tag}"
    except Exception as e:
        logger.debug(f"Rename node failed: {e}")
        return uri

def fetch_source(url_info):
    """抓取源并进行流量/时间校验"""
    idx, url = url_info
    try:
        headers = {'User-Agent': 'ClashMeta/1.16.0 v2rayN/6.23'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Fetch {url}: HTTP {resp.status_code}")
            return []
        
        content = resp.text.strip()
        
        # 流量与到期判定
        info = parse_usage_and_expire(content, resp.headers)
        u, d, total = info.get("upload", 0), info.get("download", 0), info.get("total", 0)
        expire = info.get("expire")
        now = int(time.time())

        THRESHOLD_1GB = 1024 * 1024 * 1024

        if total > 0:
            remaining = total - (u + d)
            if remaining < THRESHOLD_1GB:
                logger.info(f"Skip {url}: remaining <1GB ({remaining/1024**3:.1f}GB)")
                return []

        if expire and expire > 0 and now >= expire:
            logger.info(f"Skip {url}: expired")
            return []

        # 提取节点：先尝试 Base64 解码
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded and "://" in decoded:
                content = decoded
                logger.debug(f"Decoded base64 for {url}")

        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks5?|socks)://[^\s\'"<>]+'
        uris = re.findall(pattern, content, re.IGNORECASE)
        logger.info(f"Fetched {len(uris)} nodes from {url}")
        return uris
    except Exception as e:
        logger.warning(f"Fetch {url} failed: {e}")
        return []

def main():
    link_env = os.environ.get('LINK', '').strip()
    if not link_env:
        logger.warning("No LINK env var")
        return

    # 掩码输出订阅链接
    for line in link_env.split('\n'):
        line = line.strip()
        if line: print(f"::add-mask::{line}")

    links = [l.strip() for l in link_env.split('\n') if l.strip()]
    logger.info(f"Processing {len(links)} links")
    
    all_uris = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(fetch_source, enumerate(links))
        for r in results:
            all_uris.extend(r)
    
    if not all_uris:
        logger.warning("No valid nodes found")
        return

    unique_uris = list(set(all_uris))
    logger.info(f"Unique URIs: {len(unique_uris)}")

    # GeoIP 重命名
    reader = None
    if os.path.exists('GeoLite2-Country.mmdb'):
        try:
            reader = maxminddb.open_database('GeoLite2-Country.mmdb')
        except Exception as e:
            logger.warning(f"GeoIP DB load failed: {e}")
    
    final_uris = []
    for u in unique_uris:
        renamed = rename_node(u, reader)
        final_uris.append(renamed)
    
    if reader:
        reader.close()

    # 解析为 Clash proxies（避免重复调用）
    clash_proxies = []
    for u in final_uris:
        p = parse_uri_to_clash(u)
        if p:
            clash_proxies.append(p)

    if not clash_proxies:
        logger.warning("No valid Clash proxies")
        return

    os.makedirs('data', exist_ok=True)

    # 1. Clash YAML
    proxy_names = [p['name'] for p in clash_proxies]
    config = {
        "proxies": clash_proxies,
        "proxy-groups": [
            {
                "name": "🔰 节点选择",
                "type": "select",
                "proxies": ["🚀 自动测速", "DIRECT"] + proxy_names
            },
            {
                "name": "🚀 自动测速",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names
            }
        ],
        "rules": ["MATCH,🔰 节点选择"]
    }
    with open('data/clash.yaml', 'w', encoding='utf-8') as f:
        f.write('# profile-title: "Aggregated Subscription (Enhanced)"\n')
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    # 2. nodes.txt
    nodes_content = "\n".join(final_uris) + "\n"
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write(nodes_content)

    # 3. v2ray.txt (Base64)
    b64_content = base64.b64encode(nodes_content.encode('utf-8')).decode('utf-8')
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        f.write(b64_content)

    logger.info(f"✨ 任务完成！有效节点: {len(clash_proxies)} / {len(final_uris)}")
    print(f"✨ 任务完成！有效节点: {len(clash_proxies)}")

if __name__ == "__main__":
    main()
