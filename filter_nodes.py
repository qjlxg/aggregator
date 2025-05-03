import asyncio

async def tcp_ping(host, port, timeout=0.5):
    try:
        loop = asyncio.get_event_loop()
        fut = loop.create_connection(lambda: asyncio.Protocol(), host, port)
        _, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        return True
    except Exception:
        return False

async def batch_tcp_check(nodes, max_concurrent=100):
    sem = asyncio.Semaphore(max_concurrent)
    results = []

    async def check_one(node):
        async with sem:
            host, port = node['server'], node['port']
            try:
                if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', str(host)):
                    host = socket.gethostbyname(host)
            except Exception:
                return None
            ok = await tcp_ping(host, port)
            if ok:
                return node
            return None

    tasks = [check_one(node) for node in nodes]
    for fut in asyncio.as_completed(tasks):
        result = await fut
        if result:
            results.append(result)
    return results

def start_clash_with_all_nodes(nodes, port=BASE_PORT):
    clash_cfg = {
        'port': port,
        'socks-port': port + 1,
        'mode': 'global',
        'proxies': nodes,
        'proxy-groups': [{
            'name': 'Proxy',
            'type': 'select',
            'proxies': [n['name'] for n in nodes]
        }],
        'rules': ['MATCH,Proxy'],
        'external-controller': f'127.0.0.1:{port+234}',
        'secret': ''
    }
    fname = 'temp_all.yaml'
    with open(fname, 'w', encoding='utf-8') as f:
        yaml.dump(clash_cfg, f, allow_unicode=True)
    p = subprocess.Popen([CLASH_PATH, '-f', fname, '-d', './clash'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not wait_port(port + 1, timeout=30):
        logging.error(f"Clash 启动端口 {port+1} 超时")
        p.terminate()
        return None, fname
    time.sleep(3)
    return p, fname

def switch_proxy_api(proxy_name, port=BASE_PORT):
    url = f"http://127.0.0.1:{port+234}/proxies/Proxy"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return False
        data = r.json()
        if data.get('now') == proxy_name:
            return True
        r2 = requests.put(url, json={"name": proxy_name}, timeout=5)
        return r2.status_code == 204
    except Exception as e:
        logging.warning(f"切换节点到 {proxy_name} 失败: {e}")
        return False

def test_node_api(node, idx, port=BASE_PORT):
    proxy_name = node['name']
    if not switch_proxy_api(proxy_name, port):
        logging.warning(f"切换到节点 {proxy_name} 失败")
        return None
    proxies = {'http': f'socks5://127.0.0.1:{port + 1}', 'https': f'socks5://127.0.0.1:{port + 1}'}
    ok = False
    for _ in range(RETRY_TIMES):
        try:
            r = requests.get(TEST_URL, proxies=proxies, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if r.status_code in [200, 204, 301, 302, 403, 429]:
                ok = True
                break
        except Exception:
            continue
    if ok:
        logging.info(f"节点 {proxy_name} 测试成功")
        return node
    else:
        logging.info(f"节点 {proxy_name} 测试失败: 无法访问 {TEST_URL}")
        return None

def main():
    os.makedirs('data', exist_ok=True)
    inp = 'data/clash.yaml'
    out = 'data/google.yaml'

    d = load_yaml(inp)
    nodes = []
    for x in d.get('proxies', []):
        n = parse_url_node(x) if isinstance(x, str) else x if x.get('type') in SUPPORTED_TYPES else None
        if n:
            nodes.append(n)
    logging.info(f"加载 {len(nodes)} 个节点")

    # 1. 先做TCP检测
    logging.info("开始TCP检测...")
    tcp_valid = asyncio.run(batch_tcp_check(nodes, max_concurrent=100))
    logging.info(f"TCP检测通过节点数: {len(tcp_valid)}")

    if not tcp_valid:
        logging.info("没有通过TCP检测的节点，未生成文件。")
        return

    # 2. 批量启动Clash
    clash_proc, clash_cfg = start_clash_with_all_nodes(tcp_valid)
    if not clash_proc:
        logging.error("Clash 启动失败，无法检测")
        return

    # 3. 用Clash逐个检测
    valid = []
    for idx, node in enumerate(tcp_valid):
        node['name'] = f"bing{idx+1}"
        result = test_node_api(node, idx)
        if result:
            valid.append(result)
        time.sleep(0.5)  # 防止切换过快

    # 4. 停止Clash
    stop_clash(clash_proc, clash_cfg)

    # 5. 保存有效节点
    if valid:
        save_yaml({'proxies': valid}, out)
        logging.info(f"有效节点数: {len(valid)}")
    else:
        logging.info("没有有效节点，未生成文件。")

if __name__ == "__main__":
    main()
