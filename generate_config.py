import base64
import json
import yaml
from urllib.parse import urlparse, parse_qs

def parse_vmess(uri):
    vmess_data = base64.b64decode(uri.split("://")[1]).decode()
    vmess_config = json.loads(vmess_data)
    return {
        "name": vmess_config["ps"],
        "type": "vmess",
        "server": vmess_config["add"],
        "port": int(vmess_config["port"]),
        "uuid": vmess_config["id"],
        "alterId": int(vmess_config["aid"]),
        "cipher": "auto",
        "network": vmess_config.get("net", "tcp"),
        "tls": vmess_config.get("tls", "") == "tls",
        "ws-path": vmess_config.get("path", "/"),
        "ws-headers": {"Host": vmess_config.get("host", "")}
    }

def parse_ss(uri):
    parts = uri.split("://")[1].split("@")
    method_password = base64.b64decode(parts[0]).decode().split(":")
    server_port = parts[1].split("#")[0].split(":")  # 处理带#的情况
    return {
        "name": "ss-" + server_port[0],
        "type": "ss",
        "server": server_port[0],
        "port": int(server_port[1]),
        "cipher": method_password[0],
        "password": method_password[1]
    }

def parse_trojan(uri):
    parsed = urlparse(uri)
    return {
        "name": "trojan-" + parsed.hostname,
        "type": "trojan",
        "server": parsed.hostname,
        "port": int(parsed.port),
        "password": parsed.netloc.split("@")[0]
    }

def generate_clash_config(nodes):
    proxies = []
    for node in nodes:
        uri = node.strip()
        if uri.startswith("vmess://"):
            proxies.append(parse_vmess(uri))
        elif uri.startswith("ss://"):
            proxies.append(parse_ss(uri))
        elif uri.startswith("trojan://"):
            proxies.append(parse_trojan(uri))
        # 可扩展支持ssr://等其他协议
    config = {
        "port": 7890,
        "socks-port": 7891,
        "external-controller": "127.0.0.1:9090",
        "secret": "",
        "proxies": proxies,
        "proxy-groups": [
            {"name": "auto", "type": "select", "proxies": [p["name"] for p in proxies]}
        ],
        "rules": ["MATCH,auto"]
    }
    with open("config.yaml", "w") as f:
        yaml.dump(config, f)

with open("data/ss.txt", "r") as f:
    nodes = f.readlines()
generate_clash_config(nodes)
