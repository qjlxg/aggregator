import yaml
import subprocess
import requests
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

# Proxy types to test as specified in the prompt
# Note: "ss://" is represented as type "ss" in Clash config, "vmess://" as "vmess", etc.
# Hysteria2 is type "hysteria2"
TARGET_PROXY_TYPES = ["vmess", "ss", "vless", "trojan", "hysteria2"]

# Test URL: light, fast, returns HTTP 204 No Content on success
TEST_URL = "http://www.gstatic.com/generate_204"
REQUEST_TIMEOUT_SECONDS = 10  # Timeout for the test request
CLASH_STARTUP_WAIT_SECONDS = 3 # Time to wait for Clash to start

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
        # Assuming clash-linux is for x86_64, common for Linux servers/desktops
        # If you have a specific arm64 linux binary, add logic here
        if 'aarch64' in machine or 'arm64' in machine:
            # The prompt did not specify a clash-linux-arm binary.
            # If you have one, e.g., 'clash-linux-arm', update here.
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
        # Ensure the binary is executable
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

def test_single_proxy(proxy_config, clash_binary_path, clash_work_dir, country_mmdb_path):
    """
    Tests a single proxy node by starting a Clash instance.
    Returns True if the proxy is valid, False otherwise.
    """
    proxy_name = proxy_config.get('name', 'UnnamedProxy')
    print(f"  Testing node: {proxy_name} (type: {proxy_config.get('type')})")

    # Find free ports for Clash
    http_port = find_free_port()
    # socks_port = find_free_port() # If needed
    # external_controller_port = find_free_port() # If needed

    temp_config_content = {
        'port': http_port,
        # 'socks-port': socks_port,
        'allow-lan': False,
        'mode': 'rule', # or 'global'
        'log-level': 'silent', # or 'error' for debugging
        # 'external-controller': f'127.0.0.1:{external_controller_port}',
        'dns': {
            'enable': True,
            'ipv6': False,
            'listen': '0.0.0.0:53', # Clash might need a DNS listen port
            'nameserver': ['114.114.114.114', '8.8.8.8'],
            'fallback': ['1.1.1.1', 'dns.google:53'],
            'enhanced-mode': 'redir-host', # or fake-ip
        },
        'geoip': True, # Tells Clash to look for Country.mmdb in its data directory
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
    except IOError as e:
        print(f"    Error creating temporary config: {e}")
        return False

    clash_process = None
    try:
        # -d sets the working directory for Clash (where Country.mmdb, etc. are)
        # -f specifies the configuration file
        # Ensure paths are absolute or correctly relative
        cmd = [clash_binary_path, '-d', os.path.abspath(clash_work_dir), '-f', temp_config_file_path]
        # print(f"    Starting Clash with command: {' '.join(cmd)}")
        clash_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # print(f"    Clash PID: {clash_process.pid}. Waiting {CLASH_STARTUP_WAIT_SECONDS}s for startup...")
        time.sleep(CLASH_STARTUP_WAIT_SECONDS)

        # Check if Clash process is still running
        if clash_process.poll() is not None:
            print(f"    Error: Clash process terminated prematurely. Exit code: {clash_process.returncode}")
            # You might want to capture stderr from Clash here for detailed errors
            return False

        proxies_for_request = {
            'http': f'http://127.0.0.1:{http_port}',
            'https': f'http://127.0.0.1:{http_port}' # HTTPS requests also go through the HTTP proxy port
        }

        # print(f"    Making request to {TEST_URL} via proxy 127.0.0.1:{http_port}")
        response = requests.get(TEST_URL, proxies=proxies_for_request, timeout=REQUEST_TIMEOUT_SECONDS, verify=True)

        if response.status_code == 204:
            print(f"    SUCCESS: Node {proxy_name} is valid.")
            return True
        else:
            print(f"    FAILED: Node {proxy_name} returned status {response.status_code}.")
            return False

    except requests.exceptions.Timeout:
        print(f"    FAILED: Node {proxy_name} timed out after {REQUEST_TIMEOUT_SECONDS}s.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"    FAILED: Node {proxy_name} request error: {e}")
        return False
    except Exception as e:
        print(f"    An unexpected error occurred while testing {proxy_name}: {e}")
        return False
    finally:
        if clash_process:
            try:
                clash_process.terminate()
                clash_process.wait(timeout=5) # Wait for termination
            except subprocess.TimeoutExpired:
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

# --- Main Execution ---
def main():
    print("Starting Clash proxy node testing process...")

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

    # 3. Filter and Test Proxies
    nodes_to_test = [p for p in all_proxies if isinstance(p, dict) and p.get('type') in TARGET_PROXY_TYPES]

    if not nodes_to_test:
        print(f"No proxies matching the target types ({', '.join(TARGET_PROXY_TYPES)}) found.")
        return

    print(f"Found {len(nodes_to_test)} proxies matching target types. Starting tests...\n")

    valid_proxies_configs = []
    for i, proxy_node_config in enumerate(nodes_to_test):
        print(f"Processing proxy {i+1}/{len(nodes_to_test)}:")
        is_valid = test_single_proxy(proxy_node_config, clash_binary, CLASH_DIR, country_mmdb_full_path)
        if is_valid:
            valid_proxies_configs.append(proxy_node_config)
        print("-" * 30) # Separator

    # 4. Save Valid Proxies to output sp.yaml
    if valid_proxies_configs:
        save_valid_proxies(valid_proxies_configs, OUTPUT_YAML_PATH)
    else:
        print("\nNo valid proxies found after testing.")
        # Create an empty sp.yaml or one with an empty proxies list
        save_valid_proxies([], OUTPUT_YAML_PATH)

    print("\nProxy testing process finished.")

if __name__ == '__main__':
    # Ensure the data directory exists for output, if not already for input
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(CLASH_DIR):
        print(f"Error: Clash directory '{CLASH_DIR}' not found. Please create it and place Clash binaries and Country.mmdb inside.")
    else:
        main()
