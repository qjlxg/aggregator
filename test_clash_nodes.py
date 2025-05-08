import yaml
import subprocess
import requests
import os
import platform
import time
import shutil
import socket
import asyncio
import aiohttp

# --- Configuration ---
INPUT_YAML_PATH = os.path.join('data', 'clash.yaml')
OUTPUT_YAML_PATH = os.path.join('data', 'sp.yaml')
CLASH_DIR = 'clash'
COUNTRY_MMDB_NAME = 'Country.mmdb'
TEMP_CONFIG_NAME = 'temp_clash_test_config.yaml'

# Proxy types to test
TARGET_PROXY_TYPES = ["vmess", "ss", "vless", "trojan", "hysteria2"]

# Test URL
TEST_URL = "http://www.gstatic.com/generate_204"
REQUEST_TIMEOUT_SECONDS = 5  # Reduced timeout for faster testing
CLASH_STARTUP_WAIT_SECONDS = 2  # Reduced startup wait
CONCURRENT_TESTS = 5  # Number of proxies to test concurrently

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
        else:
            binary_path = os.path.join(CLASH_DIR, 'clash-linux')
    elif system == 'Darwin':
        if 'arm64' in machine:
            binary_path = os.path.join(CLASH_DIR, 'clash-darwin-arm')
        elif 'x86_64' in machine:
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

async def test_single_proxy(proxy_config, clash_binary_path, clash_work_dir, country_mmdb_path):
    """
    Tests a single proxy node asynchronously by starting a Clash instance.
    Returns the proxy config if valid, None otherwise.
    """
    proxy_name = proxy_config.get('name', 'UnnamedProxy')
    proxy_type = proxy_config.get('type')
    print(f"  Testing node: {proxy_name} (type: {proxy_type})")

    http_port = find_free_port()

    temp_config_content = {
        'port': http_port,
        'allow-lan': False,
        'mode': 'rule',
        'log-level': 'silent',
        'dns': {'enable': False},  # Disable DNS for simpler testing
        'geoip': True,
        'proxies': [proxy_config],
        'proxy-groups': [{'name': 'TEST_GROUP', 'type': 'select', 'proxies': [proxy_name]}],
        'rules': [f'MATCH,TEST_GROUP']
    }

    temp_config_file_path = os.path.join(clash_work_dir, TEMP_CONFIG_NAME)
    try:
        with open(temp_config_file_path, 'w', encoding='utf-8') as f:
            yaml.dump(temp_config_content, f)
    except IOError as e:
        print(f"    Error creating temporary config: {e}")
        return None

    clash_process = None
    try:
        cmd = [clash_binary_path, '-d', os.path.abspath(clash_work_dir), '-f', temp_config_file_path]
        clash_process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(CLASH_STARTUP_WAIT_SECONDS)

        if clash_process.returncode is not None:
            print(f"    Error: Clash process terminated prematurely. Exit code: {clash_process.returncode}")
            return None

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            try:
                async with session.get(TEST_URL, proxy=f'http://127.0.0.1:{http_port}', timeout=REQUEST_TIMEOUT_SECONDS) as response:
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

async def main():
    print("Starting Clash proxy node testing process...")
    print(f"Current working directory: {os.getcwd()}")  # Print current working directory

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

    # 3. Filter and Test Proxies Concurrently
    nodes_to_test = [p for p in all_proxies if isinstance(p, dict) and p.get('type') in TARGET_PROXY_TYPES]

    if not nodes_to_test:
        print(f"No proxies matching the target types ({', '.join(TARGET_PROXY_TYPES)}) found.")
        return

    print(f"Found {len(nodes_to_test)} proxies matching target types. Starting concurrent tests ({CONCURRENT_TESTS} at a time)...\n")

    valid_proxies_configs = []
    tasks = [test_single_proxy(proxy, clash_binary, CLASH_DIR, country_mmdb_full_path) for proxy in nodes_to_test]

    for i in range(0, len(tasks), CONCURRENT_TESTS):
        results = await asyncio.gather(*tasks[i:i + CONCURRENT_TESTS])
        for result in results:
            if result:
                valid_proxies_configs.append(result)
        print("-" * 30)  # Separator between batches

    # 4. Save Valid Proxies to output sp.yaml
    print(f"\nSaving valid proxies to: {OUTPUT_YAML_PATH}")  # Print output path before saving
    if valid_proxies_configs:
        save_valid_proxies(valid_proxies_configs, OUTPUT_YAML_PATH)
    else:
        print("\nNo valid proxies found after testing.")
        save_valid_proxies([], OUTPUT_YAML_PATH)

    print("\nProxy testing process finished.")

if __name__ == '__main__':
    # Ensure the data directory exists for output
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(CLASH_DIR):
        print(f"Error: Clash directory '{CLASH_DIR}' not found. Please create it and place Clash binaries and Country.mmdb inside.")
    else:
        asyncio.run(main())
