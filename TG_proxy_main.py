# coding=utf-8
import base64
import json
import logging
import os
import random
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import chardet
import requests
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("script.log"), logging.StreamHandler()]
)

# Load configuration from external file
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "update_path": "./sub/",
    "max_workers": 10,
    "subscription_urls": [
        "https://37cdn.ski9.cn",
        "http://vpn1.fengniaocloud.top",
        # Add more URLs as needed
    ],
    "channel_urls": []
}

def load_config() -> dict:
    """Load configuration from a JSON file or return default config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG

config = load_config()

class ProxyCollector:
    def __init__(self):
        self.update_path = config["update_path"]
        self.clash_subscriptions: List[str] = []
        self.v2ray_subscriptions: List[str] = []
        self.node_plaintexts: List[str] = []
        self.unique_urls: set = set()
        self.permanent_subscriptions: List[str] = []
        self.trial_subscriptions: List[str] = []
        self.trial_nodes: List[str] = []
        self.lock = threading.Lock()

    def fetch_channel_urls(self, url: str) -> List[str]:
        """Fetch HTTP URLs from a Telegram channel."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            response = requests.post(url, headers=headers, timeout=10)
            response.raise_for_status()
            pattern = r'"https+:[^\s]*"'
            return [url.replace('"', "").replace("\\", "") for url in re.findall(pattern, response.text)]
        except requests.RequestException as e:
            logging.error(f"Failed to fetch channel {url}: {e}")
            return []

    def decode_base64(self, data: str) -> Optional[str]:
        """Decode Base64 encoded data."""
        try:
            decoded_bytes = base64.b64decode(data)
            encoding = chardet.detect(decoded_bytes)["encoding"] or "utf-8"
            return decoded_bytes.decode(encoding)
        except Exception as e:
            logging.error(f"Base64 decoding failed: {e}")
            return None

    def process_subscription(self, url: str) -> None:
        """Determine if a URL is a Clash or V2Ray subscription and process it."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            content = response.text

            if "proxies:" in content:
                logging.info(f"Clash subscription found: {url}")
                with self.lock:
                    self.clash_subscriptions.append(url)
            else:
                decoded = self.decode_base64(content)
                if decoded:
                    logging.info(f"V2Ray subscription found: {url}")
                    with self.lock:
                        self.v2ray_subscriptions.append(url)
                        self.node_plaintexts.extend(decoded.splitlines())
        except requests.RequestException as e:
            logging.warning(f"Failed to process {url}: {e}")

    def collect_channel_subscriptions(self) -> None:
        """Collect subscriptions from Telegram channels using a thread pool."""
        urls = config["channel_urls"]
        if not urls:
            logging.info("No channel URLs provided.")
            return

        with ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
            future_to_url = {executor.submit(self.fetch_channel_urls, url): url for url in urls}
            for future in tqdm(future_to_url, desc="Fetching channels"):
                channel_urls = future.result()
                self.unique_urls.update([url for url in channel_urls if "t" not in url[8] and "p" not in url[-2]])

        recent_urls = list(self.unique_urls)[-25:]  # Process the last 25 URLs
        with ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
            executor.map(self.process_subscription, recent_urls)

    def fetch_airport_trial(self) -> None:
        """Fetch trial subscriptions from airport websites."""
        V2B_REG_REL_URL = "/api/v1/passport/auth/register"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        for url in config["subscription_urls"]:
            form_data = {
                "email": f"{''.join(random.choices(string.ascii_letters + string.digits, k=12))}@gmail.com",
                "password": ''.join(random.choices(string.ascii_letters + string.digits, k=12)),  # Random password
                "invite_code": "",
                "email_code": ""
            }
            try:
                response = requests.post(f"{url}{V2B_REG_REL_URL}", data=form_data, headers=headers, timeout=10)
                token = response.json()["data"]["token"]
                sub_url = f"{url}/api/v1/client/subscribe?token={token}"
                with self.lock:
                    self.trial_subscriptions.append(sub_url)
                    self.permanent_subscriptions.append(sub_url)
                logging.info(f"Trial subscription added: {sub_url}")
            except Exception as e:
                logging.error(f"Failed to fetch trial from {url}: {e}")

    def fetch_free_nodes(self) -> None:
        """Fetch free nodes from specific websites."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"
        }
        # Example: Fetch from kkzui.com
        try:
            res = requests.get("https://kkzui.com/jd?orderby=modified", headers=headers, timeout=10)
            article_url = re.search(r'<h2 class="item-heading"><a href="(https://kkzui.com/(.*?)\.html)"', res.text).group(1)
            res = requests.get(article_url, headers=headers, timeout=10)
            sub_url = re.search(r'<p><strong>这是v2订阅地址</strong>：(.*?)</p>', res.text).group(1)
            with self.lock:
                self.permanent_subscriptions.append(sub_url)
            logging.info(f"Free node from kkzui.com: {sub_url}")
        except Exception as e:
            logging.error(f"Failed to fetch from kkzui.com: {e}")

    def write_subscriptions(self) -> None:
        """Write collected subscriptions to files and update README."""
        if not (self.permanent_subscriptions or self.trial_subscriptions):
            logging.error("No subscriptions to write.")
            return

        # Process permanent subscriptions
        random.shuffle(self.permanent_subscriptions)
        for sub in self.permanent_subscriptions:
            try:
                res = requests.get(sub, timeout=10)
                nodes = self.decode_base64(res.text)
                if nodes:
                    with self.lock:
                        self.node_plaintexts.extend(nodes.splitlines())
            except Exception as e:
                logging.warning(f"Permanent subscription {sub} failed: {e}")

        # Process trial subscriptions
        random.shuffle(self.trial_subscriptions)
        for sub in self.trial_subscriptions:
            try:
                res = requests.get(sub, timeout=10)
                nodes = self.decode_base64(res.text)
                if nodes:
                    with self.lock:
                        self.trial_nodes.extend(nodes.splitlines())
            except Exception as e:
                logging.warning(f"Trial subscription {sub} failed: {e}")

        # Deduplicate and clean nodes
        unique_nodes = list(set(self.node_plaintexts))
        trial_nodes = "\n".join(self.trial_nodes).replace("\n\n", "\n")
        logging.info(f"Deduplicated {len(self.node_plaintexts) - len(unique_nodes)} nodes.")

        # Write daily subscription
        date = time.strftime("%y%m")
        date_day = time.strftime("%y%m%d")
        os.makedirs(f"{self.update_path}{date}", exist_ok=True)
        daily_file = f"{self.update_path}{date}/{date_day}.txt"
        with open(daily_file, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_nodes).replace("\n\n", "\n"))

        # Split and write long-term subscriptions
        step = max(1, len(unique_nodes) // 8 + 1)
        for i, start in enumerate(range(0, len(unique_nodes), step), 1):
            chunk = "\n".join(unique_nodes[start:start + step]).replace("\n\n", "\n")
            encoded = base64.b64encode(chunk.encode()).decode()
            with open(f"Long_term_subscription{i}", "w", encoding="utf-8") as f:
                f.write(encoded)

        # Write total long-term subscription
        total_encoded = base64.b64encode("\n".join(unique_nodes).encode()).decode()
        with open("Long_term_subscription_num", "w", encoding="utf-8") as f:
            f.write(total_encoded)

        # Write trial subscription
        trial_encoded = base64.b64encode(trial_nodes.encode()).decode()
        with open("Long_term_subscription_try", "w", encoding="utf-8") as f:
            f.write(trial_encoded)

        # Update README
        self.update_readme(len(unique_nodes), step)

        logging.info(f"Subscriptions written successfully. Total nodes: {len(unique_nodes)}")

    def update_readme(self, total_nodes: int, step: int) -> None:
        """Update README.md with subscription information."""
        try:
            with open("README.md", "r", encoding="utf-8") as f:
                lines = f.readlines()

            update_time = time.strftime("%Y-%m-%d %H:%M:%S")
            for i, line in enumerate(lines):
                if line.startswith("`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription_num`"):
                    lines[i + 1] = f"`Total number of merge nodes: {total_nodes}`\n"
                elif line.startswith("`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription"):
                    if "8" in line:
                        lines[i + 1] = f"`Total number of merge nodes: {total_nodes - step * 7}`\n"
                    else:
                        lines[i + 1] = f"`Total number of merge nodes: {step}`\n"
                elif line.startswith("`https://raw.bgithub.xyz/w1770946466/Auto_proxy/main/Long_term_subscription3.yaml`"):
                    lines[i + 4:i + 6] = [
                        f"### Try the number of high-speed subscriptions: `{len(self.trial_subscriptions)}`\n",
                        f"Updata: `{update_time}`\n"
                    ]
                elif line == ">Trial subscription：\n":
                    lines[i:i + 2] = []

            # Insert trial subscriptions
            for i, line in enumerate(lines):
                if line == "## ✨Star count\n":
                    trial_lines = [f"\n>Trial subscription：\n`{sub}`\n" for sub in self.trial_subscriptions]
                    lines[i:i] = trial_lines
                    break

            with open("README.md", "w", encoding="utf-8") as f:
                f.write("".join(lines))
        except Exception as e:
            logging.error(f"Failed to update README: {e}")

    def fetch_clash_subscriptions(self) -> None:
        """Fetch and save Clash subscriptions."""
        logging.info("Fetching Clash subscriptions.")
        for i, url in enumerate(self.clash_subscriptions, 1):
            try:
                response = requests.get(url, timeout=10)
                with open(f"Long_term_subscription{i}.yaml", "w", encoding="utf-8") as f:
                    f.write(response.text)
            except Exception as e:
                logging.error(f"Failed to fetch Clash subscription {url}: {e}")

def main():
    collector = ProxyCollector()
    logging.info("Starting proxy collection.")

    logging.info("Fetching airport trial subscriptions.")
    collector.fetch_airport_trial()

    logging.info("Fetching free nodes.")
    collector.fetch_free_nodes()

    logging.info("Fetching channel subscriptions.")
    collector.collect_channel_subscriptions()

    logging.info("Writing subscriptions.")
    collector.write_subscriptions()

    logging.info("Fetching Clash subscriptions.")
    collector.fetch_clash_subscriptions()

    logging.info("Task completed.")

if __name__ == "__main__":
    main()
