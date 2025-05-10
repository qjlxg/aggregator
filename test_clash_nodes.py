import yaml
import asyncio
import aiohttp
import subprocess
import os
import platform
import time
import shutil
import socket

# --- Configuration ---
INPUT_YAML_PATH = os.path.join('data', 'clash.yaml')
OUTPUT_YAML_PATH = os.path.join('data', 'sp.yaml')
CLASH_DIR = 'clash'
COUNTRY_MMDB_NAME = 'Country.mmdb'
TEMP_CONFIG_NAME = 'temp_clash_test_config.yaml'

TARGET_PROXY_TYPES = ["vmess", "ss", "vless", "trojan", "hysteria2"]
TEST_URL = "http://www.gstatic.com/generate_204"
REQUEST_TIMEOUT_SECONDS = 10
CLASH_STARTUP_WAIT_SECONDS = 3
MAX_CONCURRENCY = 5  # 控制并发测试的任务数量，根据系统性能调整

# --- Helper Functions ---

def find_free_port():
    """Finds an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def select_clash_binary():
    """Selects the appropriate Clash binary based on OS and architecture."""
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
    """Loads the Clash configuration from a YAML file."""
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
    """
    Tests a single proxy node by starting a Clash instance (async version).
    Returns the proxy config if valid, None otherwise.
    """
    proxy_name = proxy_config.get('name', 'UnnamedProxy')
    print(f"  Testing node: {proxy_name} (type: {proxy_config.get('type')}) - Task: {asyncio.current_task().get_name()}")

    http_port = find_free_port()

    temp_config_content = {
        'port': http_port,
        'allow-lan': False,
        'mode': 'rule',
        'log-level': 'silent',
        'dns': {
            'enable': True,
            'ipv6': False,
            'listen': '0.0.0.0:53',
            'nameserver': ['114.114.114.114', '8.8.8.8'],
            'fallback': ['1.1.1.1', 'dns.google:53'],
            'enhanced-mode': 'redir-host',
        },
        'geoip': True,
        'proxies': [proxy_config],
        'proxy-groups': [{
            'name': 'TEST_GROUP',
            'type': 'select',
            'proxies': [proxy_name]
        }],
        'rules': [f'MATCH,TEST_GROUP']
    }

    temp_config_file_path = os.path.join(clash_work_dir, TEMP_CONFIG_NAME)
    try:
        with open(temp_config_file_path, 'w', encoding='utf-8') as f:
            yaml.dump(temp_config_content, f)
        # 添加以下代码来读取并打印临时配置文件的内容
        with open(temp_config_file_path, 'r', encoding='utf-8') as f:
            temp_config_read = f.read()
            print(f"    Temporary config file content:\n{temp_config_read}")
    except IOError as e:
        print(f"    Error creating temporary config: {e}")
        return None

    clash_process = None
    try:
        cmd = [clash_binary_path, '-d', os.path.abspath(clash_work_dir), '-f', temp_config_file_path]
        clash_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,  # 捕获标准输出
            stderr=subprocess.PIPE   # 捕获标准错误
        )
        await asyncio.sleep(CLASH_STARTUP_WAIT_SECONDS)

        if clash_process.returncode is not None:
            stdout, stderr = await clash_process.communicate()
            print(f"    Error: Clash process terminated prematurely. Exit code: {clash_process.returncode}")
            if stdout:
                print(f"    Clash stdout:\n{stdout.decode()}")
            if stderr:
                print(f"    Clash stderr:\n{stderr.decode()}")
            return None

        proxies_for_request = {
            'http': f'http://127.0.0.1:{http_port}',
            'https': f'http://127.0.0.1:{http_port}'
        }

        try:
            async with session.get(TEST_URL, proxy=proxies_for_request['http'], timeout=REQUEST_TIMEOUT_SECONDS, ssl=False) as response:
                if response.status == 204:
                    print(f"    SUCCESS: Node {proxy_name} is valid.")
                    return proxy_config
                else:
                    print(f"    FAILED: Node {proxy_name} returned status {response.status}.")
                    return None
        except aiohttp.ClientError as e:
            print(f"    FAILED: Node {proxy_name} request error: {e}")
            return None
        except asyncio.TimeoutError:
            print(f"    FAILED: Node {proxy_name} timed out after {REQUEST_TIMEOUT_SECONDS}s.")
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
                print(f"    Clash process for {proxy_name} did not terminate gracefully, killing.")
                clash_process.kill()
            except Exception as e:
                print(f"    Error terminating Clash process for {proxy_name}: {e}")
        if os.path.exists(temp_config_file_path):
            try:
                os.remove(temp_config_file_path)
            except OSError as e:
                print(f"    Warning: Could not remove temporary config file {temp_config_file_path}: {e}")

def save_valid_proxies(valid_proxies, file_path):
    """Saves the list of valid proxies to a YAML file."""
    output_data = {'proxies': valid_proxies}
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(output_data, f, allow_unicode=True, sort_keys=False)
        print(f"\nSuccessfully saved {len(valid_proxies)} valid proxies to {file_path}")
    except IOError as e:
        print(f"Error: Could not write output YAML file {file_path}: {e}")

async def test_proxies_concurrently(nodes_to_test, clash_binary, clash_dir, country_mmdb_path):
    """Tests proxies concurrently using asyncio tasks."""
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

# --- Main Execution ---
async def main():
    print("Starting Clash proxy node testing process (asyncio version)...")

    # 1. Select Clash Binary
    try:
        clash_binary = select_clash_binary()
        print(f"Using Clash binary: {clash_binary}")
    except (OSError, FileNotFoundError) as e:
        print(f"Error selecting Clash binary: {e}")
        return

    # Check for Country.mmdb
    country_mmdb_full_path = os.path.abspath(os.path.join(CLASH_DIR, COUNTRY_MMDB_NAME))
    if not os.path.exists(country_mmdb_full_path):
        print(f"Error: {COUNTRY_MMDB_NAME} not found in {CLASH_DIR}/ directory.")
        print(f"Expected at: {country_mmdb_full_path}")
        return
    print(f"Found GeoIP database: {country_mmdb_full_path}")

    # 2. Load Proxies from input clash.yaml
    clash_config = load_clash_config(INPUT_YAML_PATH)
    if not clash_config or 'proxies' not in clash_config:
        print(f"No 'proxies' section found in {INPUT_YAML_PATH} or file is invalid.")
        return

    all_proxies = clash_config['proxies']
    if not isinstance(all_proxies, list):
        print(f"Error: 'proxies' section in {INPUT_YAML_PATH} is not a list.")
        return

    print(f"Loaded {len(all_proxies)} proxies from {INPUT_YAML_PATH}.")

    # 3. Filter Proxies
    nodes_to_test = [p for p in all_proxies if isinstance(p, dict) and p.get('type') in TARGET_PROXY_TYPES]

    if not nodes_to_test:
        print(f"No proxies matching the target types ({', '.join(TARGET_PROXY_TYPES)}) found.")
        return

    print(f"Found {len(nodes_to_test)} proxies matching target types. Starting concurrent tests (max {MAX_CONCURRENCY} tasks)...\n")

    # 4. Test Proxies Concurrently
    valid_proxies_configs = await test_proxies_concurrently(nodes_to_test, clash_binary, CLASH_DIR, country_mmdb_full_path)

    # 5. Save Valid Proxies to output sp.yaml
    if valid_proxies_configs:
        save_valid_proxies(valid_proxies_configs, OUTPUT_YAML_PATH)
    else:
        print("\nNo valid proxies found after testing.")
        save_valid_proxies([], OUTPUT_YAML_PATH)

    print("\nProxy testing process finished.")

if __name__ == '__main__':
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(CLASH_DIR):
        print(f"Error: Clash directory '{CLASH_DIR}' not found. Please create it and place Clash binaries and Country.mmdb inside.")
    else:
        asyncio.run(main())
