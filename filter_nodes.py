import logging
import requests
import yaml
from queue import Queue
from threading import Thread
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define test URL
TEST_URLS = {
    "GitHub": "https://www.github.com"
}

def load_nodes(input_file):
    """Load Clash nodes from a configuration file."""
    with open(input_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("proxies", [])

def test_proxy(proxy, result_queue):
    """Test the connectivity of a single proxy node."""
    try:
        proxies = {
            "http": f"http://{proxy['server']}:{proxy['port']}",
            "https": f"http://{proxy['server']}:{proxy['port']}"
        }
        success = True
        for name, url in TEST_URLS.items():
            try:
                response = requests.get(url, proxies=proxies, timeout=20)
                if response.status_code != 200:
                    success = False
                    logging.info(f"Node {proxy['name']} cannot access {name}")
                    break
            except Exception as e:
                success = False
                logging.info(f"Node {proxy['name']} failed to test {name}: {e}")
                break
        if success:
            result_queue.put(proxy)
            logging.info(f"Node {proxy['name']} passed the test")
    except Exception as e:
        logging.error(f"Error testing node {proxy['name']}: {e}")

def save_results(proxies, output_file):
    """Save the tested proxies to an output file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": proxies}, f)

def main():
    """Main function to coordinate node loading, testing, and saving results."""
    input_file = "data/clash.yaml"
    output_file = "data/google.yaml"
    
    if not os.path.exists(input_file):
        logging.error(f"Input file {input_file} does not exist")
        sys.exit(1)
    
    nodes = load_nodes(input_file)
    logging.info(f"Loaded {len(nodes)} nodes")
    
    result_queue = Queue()
    threads = []
    for node in nodes:
        t = Thread(target=test_proxy, args=(node, result_queue))
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    
    available_proxies = []
    while not result_queue.empty():
        available_proxies.append(result_queue.get())
    
    if available_proxies:
        save_results(available_proxies, output_file)
        logging.info(f"Found {len(available_proxies)} available nodes")
    else:
        logging.warning("No available nodes found, generating an empty file")
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump({"proxies": []}, f)

if __name__ == "__main__":
    main()
