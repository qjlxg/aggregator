import yaml
import asyncio
import aiohttp
import subprocess
import os
import platform
import socket

# --- 配置 ---
INPUT_YAML_PATH = os.path.join('data', 'clash.yaml')
OUTPUT_YAML_PATH = os.path.join('data', 'sp.yaml')
CLASH_DIR = 'clash'
COUNTRY_MMDB_NAME = 'Country.mmdb'

TARGET_PROXY_TYPES = ["vmess", "ss", "vless", "trojan", "hysteria2"]
TEST_URL = "http://www.gstatic.com/generate_204"
REQUEST_TIMEOUT_SECONDS = 10
CLASH_STARTUP_WAIT_SECONDS = 3
MAX_CONCURRENCY = 5

# --- 辅助函数 ---

def find_free_port():
    """查找一个可用的本地端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def select_clash_binary():
    """根据操作系统和架构选择合适的 Clash 二进制文件。"""
    system = platform.system()
    machine = platform.machine()
    binary_path = None

    if system == 'Linux':
        if 'aarch64' in machine or 'arm64' in machine:
            print("Warning: No specific ARM64 Linux Clash binary specified in prompt. Trying generic 'clash-linux'.")
            binary_path = os.path.join(CLASH_DIR, 'clash-linux')
        else: # x86_64, amd64
            binary_path = os.path.join(CLASH_DIR, 'clash-linux')
    elif system == 'Darwin': # macOS
        if 'arm64' in machine: # Apple Silicon
            binary_path = os.path.join(CLASH_DIR, 'clash-darwin-arm')
        elif 'x86_64' in machine: # Intel
            binary_path = os.path.join(CLASH_DIR, 'clash-darwin-amd')
    else:
        raise OSError(f"Unsupported operating system: {system}")

    if binary_path and os.path.exists(binary_path):
        try:
            os.chmod(binary_path, 0o755)
        except OSError as e:
            print(f"Warning: Could not set executable permission on {binary_path}: {e}")
        return os.path.abspath(binary_path)
    elif binary_path:
        raise FileNotFoundError(f"Clash binary not found at: {binary_path}")
    else:
        raise OSError(f"Could not determine Clash binary for {system} {machine}")

def load_clash_config(file_path):
    """从 YAML 文件加载 Clash 配置。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Input YAML file not found at {file_path}")
        return None
    except yaml.YAMLError as e:
        print(f"Error: Could not parse input YAML file {file_path}: {e}")
        return None

async def test_single_proxy(proxy_config, clash_binary_path, clash_work_dir, country_mmdb_path, session):
    """测试单个代理节点，直接启动 Clash 并通过其测试连接。"""
    proxy_name = proxy_config.get('name', 'UnnamedProxy')
    proxy_type = proxy_config.get('type')
    print(f"  Testing node: {proxy_name} (type: {proxy_type}) - Task: {asyncio.current_task().get_name()}")

    http_port = find_free_port()

    min_config = {
        'port': http_port,
        'allow-lan': False,
        'mode': 'rule',
        'log-level': 'silent',
        'proxies': [proxy_config],
        'proxy-groups': [{
            'name': 'TEST_GROUP',
            'type': 'select',
            'proxies': [proxy_name]
        }],
        'rules': [f'MATCH,TEST_GROUP']
    }

    config_string = yaml.dump(min_config).encode('utf-8')

    clash_process = None
    try:
        cmd = [clash_binary_path, '-d', os.path.abspath(clash_work_dir), '-f', '-'] # 使用 '-' 从 stdin 读取配置
        clash_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(clash_process.communicate(input=config_string), timeout=CLASH_STARTUP_WAIT_SECONDS)

        if clash_process.returncode != 0:
            print(f"    Error starting Clash for {proxy_name}. Exit code: {clash_process.returncode}")
            if stdout:
                print(f"    Clash stdout:\n{stdout.decode()}")
            if stderr:
                print(f"    Clash stderr:\n{stderr.decode()}")
            return None

        proxies = {'http': f'http://127.0.0.1:{http_port}', 'https': f'http://127.0.0.1:{http_port}'}
        async with session.get(TEST_URL, proxy=proxies['http'], timeout=REQUEST_TIMEOUT_SECONDS, ssl=False) as response:
            if response.status == 204:
                print(f"    SUCCESS: Node {proxy_name} is valid.")
                return proxy_config
            else:
                print(f"    FAILED: Node {proxy_name} returned status {response.status}.")
                return None

    except asyncio.TimeoutError:
        print(f"    FAILED: Timeout while starting Clash or testing {proxy_name}.")
        return None
    except aiohttp.ClientError as e:
        print(f"    FAILED: Request error for {proxy_name}: {e}")
        return None
    except Exception as e:
        print(f"    An unexpected error occurred while testing {proxy_name}: {e}")
        return None
    finally:
        if clash_process:
            try:
                clash_process.terminate()
                await asyncio.wait_for(clash_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                clash_process.kill()

async def test_proxies_concurrently(nodes_to_test, clash_binary, clash_dir, country_mmdb_path):
    """并发测试代理节点。"""
    valid_proxies_configs = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def limited_test(proxy_config):
        async with semaphore:
            async with aiohttp.ClientSession() as session:
                result = await test_single_proxy(proxy_config, clash_binary, clash_dir, country_mmdb_path, session)
                if result:
                    valid_proxies_configs.append(result)

    tasks = [limited_test(proxy) for proxy in nodes_to_test]
    await asyncio.gather(*tasks)
    return valid_proxies_configs

def save_valid_proxies(valid_proxies, file_path):
    """保存有效的代理节点到 YAML 文件。"""
    output_data = {'proxies': valid_proxies}
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(output_data, f, allow_unicode=True, sort_keys=False)
        print(f"\nSuccessfully saved {len(valid_proxies)} valid proxies to {file_path}")
    except IOError as e:
        print(f"Error: Could not write output YAML file {file_path}: {e}")

async def main():
    print("Starting Clash proxy node testing process (rebooted)...")

    # 1. 选择 Clash 二进制文件
    try:
        clash_binary = select_clash_binary()
        print(f"Using Clash binary: {clash_binary}")
    except (OSError, FileNotFoundError) as e:
        print(f"Error selecting Clash binary: {e}")
        return

    # 2. 检查 GeoIP 数据库
    country_mmdb_full_path = os.path.abspath(os.path.join(CLASH_DIR, COUNTRY_MMDB_NAME))
    if not os.path.exists(country_mmdb_full_path):
        print(f"Error: {COUNTRY_MMDB_NAME} not found in {CLASH_DIR}/ directory.")
        print(f"Expected at: {country_mmdb_full_path}")
        return
    print(f"Found GeoIP database: {country_mmdb_full_path}")

    # 3. 加载代理配置
    clash_config = load_clash_config(INPUT_YAML_PATH)
    if not clash_config or 'proxies' not in clash_config:
        print(f"No 'proxies' section found in {INPUT_YAML_PATH} or file is invalid.")
        return

    all_proxies = clash_config['proxies']
    if not isinstance(all_proxies, list):
        print(f"Error: 'proxies' section in {INPUT_YAML_PATH} is not a list.")
        return

    print(f"Loaded {len(all_proxies)} proxies from {INPUT_YAML_PATH}.")

    # 4. 筛选需要测试的代理节点
    nodes_to_test = [p for p in all_proxies if isinstance(p, dict) and p.get('type') in TARGET_PROXY_TYPES]

    if not nodes_to_test:
        print(f"No proxies matching the target types ({', '.join(TARGET_PROXY_TYPES)}) found.")
        return

    print(f"Found {len(nodes_to_test)} proxies matching target types. Starting concurrent tests (max {MAX_CONCURRENCY} tasks)...\n")

    # 5. 并发测试代理节点
    valid_proxies_configs = await test_proxies_concurrently(nodes_to_test, clash_binary, CLASH_DIR, country_mmdb_full_path)

    # 6. 保存有效的代理节点
    if valid_proxies_configs:
        save_valid_proxies(valid_proxies_configs, OUTPUT_YAML_PATH)
    else:
        print("\nNo valid proxies found after testing.")
        save_valid_proxies([], OUTPUT_YAML_PATH)

    print("\nProxy testing process finished (rebooted).")

if __name__ == '__main__':
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(CLASH_DIR):
        print(f"Error: Clash directory '{CLASH_DIR}' not found. Please create it and place Clash binaries and Country.mmdb inside.")
    else:
        asyncio.run(main())
