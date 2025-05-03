import os
import json
import base64
import urllib.parse
import yaml
import subprocess
import time
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import requests

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量
BASE_PORT = 10000
TEST_URLS = ["https://www.google.com", "https://www.youtube.com"]  # 测试 Google 和 YouTube
SUPPORTED_TYPES = ['vmess', 'ss', 'trojan', 'vless', 'hysteria2']


def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_yaml(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)
    logging.info(f"已保存 {path}")


def parse_url_node(url):
    try:
        if url.startswith('vmess://'):
            data = json.loads(base64.b64decode(url[8:]).decode())
            return {'name': data.get('ps'), 'type':'vmess', 'server':data['add'], 'port':int(data['port']), 'uuid':data['id'], 'alterId':int(data.get('aid',0)), 'cipher':data.get('scy','auto'), 'network':data.get('net','tcp'), 'tls':bool(data.get('tls',False))}
        if url.startswith('ss://'):
            parsed = urllib.parse.urlparse(url)
            method_pass = base64.b64decode(parsed.netloc.split('@')[0]).decode()
            method,passwd = method_pass.split(':')
            server,port = parsed.netloc.split('@')[1].split(':')
            return {'name':urllib.parse.unquote(parsed.fragment) or 'ss', 'type':'ss', 'server':server, 'port':int(port), 'cipher':method, 'password':passwd}
        if url.startswith('trojan://'):
            p = urllib.parse.urlparse(url)
            pwd = p.netloc.split('@')[0]
            server,port = p.netloc.split('@')[1].split(':')
            return {'name':urllib.parse.unquote(p.fragment) or 'trojan', 'type':'trojan', 'server':server, 'port':int(port), 'password':pwd, 'sni':server}
        if url.startswith('vless://'):
            p = urllib.parse.urlparse(url)
            uuid = p.netloc.split('@')[0]
            server,port = p.netloc.split('@')[1].split(':')
            return {'name':urllib.parse.unquote(p.fragment) or 'vless', 'type':'vless', 'server':server, 'port':int(port), 'uuid':uuid, 'tls':True, 'servername':server}
        if url.startswith('hysteria2://'):
            p = urllib.parse.urlparse(url)
            pwd = p.netloc.split('@')[0]
            server,port = p.netloc.split('@')[1].split(':')
            return {'name':urllib.parse.unquote(p.fragment) or 'hysteria2', 'type':'hysteria2', 'server':server, 'port':int(port), 'password':pwd}
    except Exception as e:
        logging.warning(f"解析节点失败: {e}")
    return None


def start_clash(node, port):
    cfg = {'port':port, 'socks-port':port+1, 'mode':'global', 'proxies':[node], 'proxy-groups':[{'name':'Proxy','type':'select','proxies':[node['name']]}], 'rules':['MATCH,Proxy']}
    fname = f'temp_{port}.yaml'
    with open(fname,'w',encoding='utf-8') as f: yaml.dump(cfg,f,allow_unicode=True)
    p = subprocess.Popen(['./clash/clash-linux','-f',fname,'-d','clash'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    time.sleep(5)
    return p, fname


def stop_clash(p, fname):
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except: pass
    if os.path.exists(fname): os.remove(fname)


def test_node(node, idx):
    port = BASE_PORT + (idx % 10) * 2
    p, cfg = start_clash(node, port)
    ok = True
    for url in TEST_URLS:
        try:
            r = requests.get(url, proxies={'http':f'socks5://127.0.0.1:{port+1}','https':f'socks5://127.0.0.1:{port+1}'}, timeout=15)
            if r.status_code != 200:
                ok = False
                break
        except:
            ok = False
            break
    stop_clash(p, cfg)
    if ok: return node
    return None


def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'
    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies',[]):
        n = parse_url_node(x) if isinstance(x,str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n: nodes.append(n)
    valid = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as ex:
        for idx,node in enumerate(nodes):
            valid_node = ex.submit(test_node,node,idx).result()
            if valid_node: valid.append(valid_node)
    if valid:
        save_yaml({'proxies': valid}, out)
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
