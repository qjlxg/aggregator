import os
import re
import asyncio
import logging
from urllib.parse import urlparse

import requests
from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChannelInvalidError, ChannelPrivateError
from telethon.tl.types import PeerChannel

# --- Configuration ---
# Get credentials from environment variables (best for GitHub Actions)
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE') # Or Bot Token if using a bot
SESSION_NAME = "telegram_session" # Name for the session file

# Target Telegram channel(s) - use the username or t.me link
# Example: 'mychannelusername' or 'https://t.me/mychannelusername'
# Can be a list: ['channel1', 'channel2']
TARGET_CHANNELS = ['jichang_list'] # <<< --- CHANGE THIS TO YOUR TARGET CHANNEL(S)

OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "t.txt")
PAGINATION_LIMIT = 1000 # How many messages to fetch per channel (None for all)
REQUEST_TIMEOUT = 5 # Seconds to wait for URL connection test
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" # Mimic browser

# URL Regex (adjust if needed)
URL_REGEX = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

# Set for storing unique, valid URLs
found_urls = set()

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def is_url_reachable(url):
    """Checks if a URL is reachable by sending a HEAD request."""
    try:
        # Use HEAD request to be lighter, fall back to GET if HEAD is disallowed
        headers = {'User-Agent': USER_AGENT}
        response = requests.head(url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True)
        # Consider any 2xx or 3xx status code as reachable
        if response.status_code < 400:
            logger.debug(f"URL reachable (HEAD {response.status_code}): {url}")
            return True
        else:
             # Some servers block HEAD, try GET
             logger.debug(f"HEAD failed ({response.status_code}) for {url}, trying GET...")
             response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True, stream=True) # stream=True avoids downloading large files
             if response.status_code < 400:
                 logger.debug(f"URL reachable (GET {response.status_code}): {url}")
                 return True
             else:
                 logger.warning(f"URL unreachable ({response.status_code}): {url}")
                 return False

    except requests.exceptions.Timeout:
        logger.warning(f"URL timed out: {url}")
        return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"URL error ({type(e).__name__}): {url}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking URL {url}: {e}")
        return False

def extract_urls(text):
    """Extracts URLs from a given text using regex."""
    if not text:
        return []
    return re.findall(URL_REGEX, text)

async def process_channel(client, channel_entity):
    """Fetches messages, extracts, validates, and collects URLs from a channel."""
    processed_count = 0
    added_count = 0
    logger.info(f"Starting processing for channel: {channel_entity.title}")

    try:
        async for message in client.iter_messages(channel_entity, limit=PAGINATION_LIMIT):
            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Processed {processed_count} messages in {channel_entity.title}...")

            urls_in_message = extract_urls(message.text)
            if not urls_in_message:
                continue

            for url in urls_in_message:
                # Basic check to see if it's potentially valid and not processed
                if url not in found_urls:
                    # --- Filter out t.me links ---
                    parsed_url = urlparse(url)
                    if parsed_url.netloc.lower() == 't.me':
                        logger.debug(f"Skipping t.me URL: {url}")
                        continue

                    # --- Test connectivity ---
                    # Note: This is synchronous and can block the async loop.
                    # For high performance, consider aiohttp or running requests in a thread pool.
                    if is_url_reachable(url):
                        logger.info(f"Found valid URL: {url}")
                        found_urls.add(url)
                        added_count += 1
                    # else: URL is unreachable or invalid, already logged by is_url_reachable

        logger.info(f"Finished processing {channel_entity.title}. Processed {processed_count} messages, added {added_count} new valid URLs.")

    except FloodWaitError as e:
        logger.error(f"Flood wait error for {channel_entity.title}: waiting {e.seconds} seconds.")
        await asyncio.sleep(e.seconds + 5) # Wait a bit longer
        # Optionally retry processing the channel here
    except Exception as e:
        logger.error(f"Error processing channel {channel_entity.title}: {e}")


async def main():
    """Main function to connect, process channels, and save results."""
    if not all([API_ID, API_HASH]):
        logger.error("API_ID and API_HASH must be set as environment variables.")
        return
    if not PHONE_NUMBER:
        logger.warning("PHONE_NUMBER environment variable not set. Trying anonymous login or existing session.")
        # Note: Anonymous login might have limitations on accessing certain public channels.

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Initialize Telegram client
    # Use sync version here for simplicity in the main setup part,
    # but leverage async methods like iter_messages later.
    # Note: The first run might require interactive login (phone code/password)
    # if session file doesn't exist or is invalid. This is problematic for GitHub Actions.
    # Best practice for Actions: Generate session locally, store SESSION_STRING env var.
    logger.info("Initializing Telegram client...")
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    try:
        logger.info("Connecting to Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            logger.info("Not authorized. Attempting to sign in...")
            if PHONE_NUMBER:
                 await client.send_code_request(PHONE_NUMBER)
                 try:
                     await client.sign_in(PHONE_NUMBER, input('Enter the code sent to your Telegram: '))
                 except SessionPasswordNeededError:
                     await client.sign_in(password=input('Enter your Telegram password: '))
                 logger.info("Signed in successfully.")
            else:
                logger.error("Cannot sign in without PHONE_NUMBER. Exiting.")
                await client.disconnect()
                return
        else:
            logger.info("Already authorized.")

        # --- Process Channels ---
        for target in TARGET_CHANNELS:
            logger.info(f"Attempting to get entity for: {target}")
            try:
                # Handle both usernames and t.me links
                if target.startswith(('http://', 'https://')):
                    channel_input = target.split('/')[-1]
                else:
                    channel_input = target

                entity = await client.get_entity(channel_input)
                # Ensure it's a channel we can read from
                if isinstance(entity, PeerChannel) or hasattr(entity, 'title'): # Check if it looks like a channel/chat
                     await process_channel(client, entity)
                else:
                     logger.warning(f"Entity '{target}' is not a recognized channel or chat. Skipping.")

            except (ValueError, ChannelInvalidError):
                logger.error(f"Channel '{target}' not found or invalid.")
            except ChannelPrivateError:
                logger.error(f"Channel '{target}' is private and cannot be accessed.")
            except FloodWaitError as e:
                 logger.error(f"Flood wait error while getting entity for {target}: waiting {e.seconds} seconds.")
                 await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                logger.error(f"Could not get entity for '{target}': {e}")

        # --- Save Results ---
        logger.info(f"Total unique, valid, non-t.me URLs found: {len(found_urls)}")
        if found_urls:
            logger.info(f"Saving URLs to {OUTPUT_FILE}...")
            # Sort for consistency (optional)
            sorted_urls = sorted(list(found_urls))
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for url in sorted_urls:
                    f.write(url + '\n')
            logger.info("URLs saved successfully.")
        else:
            logger.info("No valid URLs found to save.")

    except Exception as e:
        logger.exception(f"An unexpected error occurred in main: {e}")
    finally:
        if client.is_connected():
            logger.info("Disconnecting Telegram client...")
            await client.disconnect()
            logger.info("Client disconnected.")

if __name__ == "__main__":
    asyncio.run(main())
