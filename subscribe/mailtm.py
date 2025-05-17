# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import gzip
import json
import random
import re
import time
import urllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO, Dict, Optional # Added Optional

import utils
from logger import logger


@dataclass
class Message:
    """simple data class that holds a message information."""

    text: str
    id: str = ""
    sender: Optional[Dict] = None
    to: Optional[Dict] = None
    subject: str = ""
    intro: str = ""
    html: str = ""
    data: Optional[Dict] = None


@dataclass
class Account:
    """representing a temprary mailbox."""

    address: str
    password: str = ""
    id: str = ""


class TemporaryMail(object):
    """temporary mails collctions: https://www.cnblogs.com/perfectdata/p/15902582.html"""

    def __init__(self) -> None:
        self.api_address = ""

    def get_domains_list(self) -> list:
        raise NotImplementedError

    def get_account(self, max_retries: int = 3) -> Optional[Account]:
        raise NotImplementedError

    def get_messages(self, account: Account) -> list:
        raise NotImplementedError

    def monitor_account(self, account: Account, timeout: int = 300, sleep: int = 3) -> Optional[Message]:
        """keep waiting for new messages"""
        if not account:
            logger.warning("monitor_account called with no account.")
            return None

        timeout = min(600, max(0, timeout))
        sleep = min(max(1, sleep), 10)
        
        try:
            initial_messages = self.get_messages(account=account)
            if initial_messages is None: # Defensive check
                logger.warning(f"Initial get_messages returned None for {account.address}")
                initial_messages = []
            
            start_count = len(initial_messages)
            latest_messages_list = initial_messages
            
            endtime = time.time() + timeout
            while time.time() < endtime:
                current_messages_list = self.get_messages(account=account)
                if current_messages_list is None: # Defensive check
                    logger.warning(f"Subsequent get_messages returned None for {account.address}")
                    current_messages_list = [] # Treat as empty list to avoid errors

                if len(current_messages_list) > start_count:
                    # New messages have arrived. Return the first of the new messages.
                    # Assuming new messages are appended to the list.
                    return current_messages_list[start_count]

                latest_messages_list = current_messages_list
                
                if time.time() >= endtime: # Check time again after potentially long get_messages call
                    break
                
                time.sleep(sleep)

            # Timeout reached or no new messages.
            if latest_messages_list:
                # Fallback: return the first message of the latest list if any messages exist
                return latest_messages_list[0]
            
            logger.info(f"No messages found for {account.address} after monitoring period or no new messages.")
            return None

        except Exception as e:
            logger.error(f"Error monitoring account {account.address}: {e}", exc_info=True)
            return None

    def delete_account(self, account: Account) -> bool:
        raise NotImplementedError

    def extract_mask(self, text: str, regex: str = "您的验证码是：([0-9]{6})") -> str:
        if not text or not regex:
            return ""
        try:
            masks = re.findall(regex, text)
            return masks[0] if masks else ""
        except re.error as e:
            logger.error(f"[MaskExtractError] Regex error for regex '{regex}': {e}")
            return ""
        except Exception as e:
            logger.error(f"[MaskExtractError] Unexpected error during mask extraction with regex '{regex}': {e}", exc_info=True)
            return ""

    def generate_address(self, bits: int = 10) -> str:
        bits = min(max(6, bits), 16)
        username = utils.random_chars(length=bits, punctuation=False).lower()
        
        # get_domains_list might involve retries internally if overridden
        email_domains = self.get_domains_list()
        if not email_domains:
            logger.error(f"[{self.__class__.__name__}Error] Cannot find any email domains from remote, domain source: {self.api_address}")
            return ""

        domain = random.choice(email_domains)
        address = f"{username}@{domain}"
        return address


class RootSh(TemporaryMail):
    def __init__(self) -> None:
        super().__init__()
        self.api_address = "https://rootsh.com"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": utils.USER_AGENT,
        }

    def _decode_response(self, response_bytes: bytes) -> str:
        try:
            return gzip.decompress(response_bytes).decode("utf8")
        except (gzip.BadGzipFile, EOFError, TypeError):
            try:
                return response_bytes.decode("utf8")
            except UnicodeDecodeError as e:
                logger.warning(f"RootSh: UTF-8 decode failed: {e}. Response (partial): {response_bytes[:100]}")
                return ""
        except UnicodeDecodeError as e:
            logger.warning(f"RootSh: UTF-8 decode failed after gzip: {e}.")
            return ""

    def get_domains_list(self, max_retries: int = 3) -> list:
        content = ""
        for attempt in range(max_retries):
            try:
                request = urllib.request.Request(url=self.api_address, headers=self.headers)
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
                
                new_cookie = response.getheader("Set-Cookie")
                if new_cookie:
                    self.headers["Cookie"] = new_cookie 

                response_bytes = response.read()
                content = self._decode_response(response_bytes)
                
                if content:
                    break 
            
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"RootSh get_domains_list: network error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"RootSh get_domains_list: failed after {max_retries} attempts due to network issues.")
                    return []
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.error(f"RootSh get_domains_list: unexpected error on attempt {attempt + 1}/{max_retries}: {e}", exc_info=True)
                if attempt == max_retries - 1:
                    return []
        
        if not content:
            logger.error("RootSh get_domains_list: failed to retrieve content after all retries.")
            return []

        try:
            return re.findall(r'<li><a\s+href="javascript:;">([a-zA-Z0-9\.\-]+)</a></li>', content)
        except re.error as e:
            logger.error(f"RootSh get_domains_list: regex error: {e}")
            return []

    def get_account(self, max_retries: int = 3) -> Optional[Account]:
        address = self.generate_address(random.randint(6, 12))
        if not address:
            logger.error("[RootShError] Failed to generate an email address for RootSh.")
            return None

        url = f"{self.api_address}/applymail"
        params = {"mail": address}
        
        current_headers = self.headers.copy()
        current_headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.api_address,
            "Referer": f"{self.api_address}/",
        })

        for attempt in range(max_retries):
            try:
                data = urllib.parse.urlencode(params).encode(encoding="UTF8")
                request = urllib.request.Request(url, data=data, headers=current_headers, method="POST")
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

                if response.getcode() == 200:
                    response_data = response.read()
                    decoded_content = self._decode_response(response_data)
                    if not decoded_content:
                        logger.error(f"[RootShError] RootSh account creation failed for {address}, empty or undecodable response, attempt {attempt + 1}/{max_retries}")
                        return None # Or continue to retry if appropriate

                    try:
                        success = json.loads(decoded_content).get("success", "false")
                        if success == "true":
                            return Account(address=address)
                        else:
                            logger.warning(f"[RootShError] RootSh account creation not successful for {address} (success={success}), attempt {attempt + 1}/{max_retries}")
                            return None # API indicated failure, no need to retry this specific response
                    except json.JSONDecodeError:
                        logger.error(f"[RootShError] RootSh account creation failed for {address}, invalid JSON response: {decoded_content[:200]}..., attempt {attempt + 1}/{max_retries}")
                        return None # JSON error, no need to retry this specific response
                else:
                    error_body = response.read().decode('UTF8', errors='ignore')[:200]
                    logger.error(
                        f"[RootShError] RootSh: cannot create email account for {address}, status: {response.getcode()}, message: {error_body}..., attempt {attempt + 1}/{max_retries}"
                    )
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"[RootShError] RootSh: network error creating account for {address} (attempt {attempt + 1}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"[RootShError] RootSh: unexpected error creating account for {address} (attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)
            
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        logger.error(f"[RootShError] RootSh: failed to create account for {address} after {max_retries} attempts.")
        return None

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        url = f"{self.api_address}/getmail"
        params = {
            "mail": account.address,
            "time": 0, # Original code had self.timestamp, then this 0. 'time' might be for fetching since a timestamp.
            "_": int(time.time() * 1000),
        }

        messages = []
        try:
            # Headers for this request might need specific Accept for JSON if different from self.headers
            # Assuming self.headers (with potential cookie from get_domains_list) is suitable
            post_headers = self.headers.copy()
            post_headers["Accept"] = "application/json, text/javascript, */*; q=0.01" # As in get_account
            post_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"


            data = urllib.parse.urlencode(params).encode(encoding="UTF8")
            request = urllib.request.Request(url, data=data, headers=post_headers, method="POST")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

            if response.getcode() == 200:
                response_data = response.read()
                decoded_content = self._decode_response(response_data)
                if not decoded_content:
                    logger.error(f"[RootShError] Failed to get messages for {account.address}, empty or undecodable list response.")
                    return []
                
                data = json.loads(decoded_content)
                success = data.get("success", "false")
                if success == "true":
                    emails = data.get("mail", [])
                    for mail_item in emails: # Renamed mail to mail_item to avoid conflict
                        sender = {mail_item[1]: f"{mail_item[0]}<{mail_item[1]}>"}
                        subject = mail_item[2]
                        # address_encoded = account.address.replace("@", "(a)").replace(".", "-_-") # Original had 'address' not 'address_encoded'
                        address_encoded = account.address.replace("@", "(a)").replace(".", "-_-")


                        # Fetch individual mail content
                        mail_url = f"{self.api_address}/win/{address_encoded}/{mail_item[4]}"
                        # Headers for fetching individual mail content
                        mail_headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                            "User-Agent": utils.USER_AGENT,
                            # Cookie from self.headers might be needed here too
                            "Cookie": self.headers.get("Cookie", "") 
                        }
                        
                        # utils.http_get is external, assuming it handles retries and decoding
                        mail_content = utils.http_get(url=mail_url, headers=mail_headers)
                        if mail_content is None: # Check if http_get can return None
                            mail_content = ""
                            logger.warning(f"Failed to fetch content for mail ID {mail_item[4]} from {mail_url}")

                        messages.append(
                            Message(
                                sender=sender,
                                to={account.address: account.address},
                                subject=subject,
                                intro=mail_item[0],
                                text=mail_content,
                                html=mail_content,
                            )
                        )
            else:
                logger.info(
                    f"[RootShError] Cannot get mail list from domain: {self.api_address}, email: {account.address}, status: {response.getcode()}"
                )
        except json.JSONDecodeError as je:
            logger.error(f"[RootShError] JSON decode error while fetching messages for {account.address}: {je}", exc_info=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as ne:
            logger.error(f"[RootShError] Network error fetching messages for {account.address}: {ne}", exc_info=True)
        except Exception as e:
            logger.error(f"[RootShError] Unexpected error fetching messages for {account.address}: {e}", exc_info=True)
        
        return messages

    def delete_account(self, account: Account, max_retries: int = 3) -> bool:
        if not account: return False
        url = f"{self.api_address}/destroymail"
        params = {"_": int(time.time() * 1000)}
        
        delete_headers = self.headers.copy()
        delete_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        delete_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"


        for attempt in range(max_retries):
            try:
                data = urllib.parse.urlencode(params).encode(encoding="UTF8")
                request = urllib.request.Request(url, data=data, headers=delete_headers, method="POST")
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

                if response.getcode() == 200:
                    response_data = response.read()
                    decoded_content = self._decode_response(response_data)
                    if not decoded_content:
                        logger.error(f"[RootShError] Delete account {account.address} failed, empty/undecodable response.")
                        return False

                    success = json.loads(decoded_content).get("success", "false")
                    return success == "true"
                else:
                    logger.warning(f"[RootShError] Delete account {account.address} failed with status {response.getcode()}, attempt {attempt+1}/{max_retries}")
            
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                logger.warning(f"[RootShError] Error deleting account {account.address} (attempt {attempt+1}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"[RootShError] Unexpected error deleting account {account.address} (attempt {attempt+1}/{max_retries}): {e}", exc_info=True)

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1,2))
        
        logger.error(f"[RootShError] Delete account {account.address} failed after {max_retries} attempts.")
        return False


class SnapMail(TemporaryMail):
    def __init__(self) -> None:
        super().__init__()
        self.api_address = "https://snapmail.cc"

    def get_domains_list(self) -> list:
        # Domains seem relatively static based on original code
        return ["snapmail.cc", "lista.cc", "xxxhi.cc"]

    def get_account(self, max_retries: int = 3) -> Optional[Account]: # Added max_retries for consistency
        address = self.generate_address(bits=random.randint(6, 12))
        if not address:
            logger.error("[SnapMailError] Failed to generate address for SnapMail.")
            return None
        return Account(address=address)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        url = f"{self.api_address}/emaillist/{account.address}"
        # utils.http_get is external, assuming it handles retries, decoding, and returns str or None
        content_str = utils.http_get(url=url, retry=1) # Original used retry=1
        
        if not content_str:
            logger.warning(f"[SnapMailError] No content received from {url}")
            return []
        
        messages = []
        try:
            emails = json.loads(content_str)
            for email in emails:
                html = email.get("html", "")
                if not html:
                    continue
                senders = email.get("from", [])
                sender_dict = senders[0] if senders and isinstance(senders[0], dict) else {}
                
                messages.append(
                    Message(
                        id=email.get("id", ""),
                        sender=sender_dict,
                        to={account.address: account.address}, # Corrected to dict
                        subject=email.get("subject", ""),
                        text=html,
                        html=html,
                    )
                )
        except json.JSONDecodeError as je:
            logger.error(f"[SnapMailError] JSON decode error for {account.address}: {je}. Content: {content_str[:200]}...")
        except Exception as e:
            logger.error(f"[SnapMailError] Error processing messages for {account.address}: {e}", exc_info=True)
            
        return messages

    def delete_account(self, account: Account) -> bool:
        # Original code stated not supported.
        logger.info(f"[SnapMailInfo] SnapMail does not support account deletion via this API implementation for {account.address}.")
        return False # Or True if "not supported but successful" is the meaning


class LinShiEmail(TemporaryMail):
    def __init__(self) -> None:
        super().__init__()
        self.api_address = "https://linshiyouxiang.net"

    def get_domains_list(self) -> list:
        content = utils.http_get(url=self.api_address) # Assumes http_get returns str or None
        if not content:
            logger.error("[LinShiEmailError] Failed to fetch main page for domains.")
            return []

        try:
            domains = re.findall(r'data-mailhost="@([a-zA-Z0-9\-_\.]+)"', content)
            if "idrrate.com" in domains: # As per original comment
                domains.remove("idrrate.com")
            return domains
        except re.error as e:
            logger.error(f"[LinShiEmailError] Regex error while parsing domains: {e}")
            return []

    def get_account(self, max_retries: int = 3) -> Optional[Account]: # Added max_retries for consistency
        address = self.generate_address(bits=random.randint(6, 12))
        if not address:
            logger.error("[LinShiEmailError] Failed to generate address.")
            return None
        return Account(address=address)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        username = account.address.split("@", maxsplit=1)[0]
        url = f"{self.api_address}/api/v1/mailbox/{username}"
        
        content_str = utils.http_get(url=url, retry=1) # Assumes http_get returns str or None
        if not content_str:
            logger.warning(f"[LinShiEmailError] No message list content from {url}")
            return []

        messages = []
        try:
            emails = json.loads(content_str)
            for email_data in emails: # Renamed email to email_data
                mail_id = email_data.get("id", "")
                sender_str = email_data.get("from", "") # This is usually a string like "Sender <sender@example.com>"
                if not mail_id:
                    continue

                # Fetch individual mail content
                mail_content_url = f"{self.api_address}/mailbox/{username}/{mail_id}"
                # utils.http_get for mail content
                individual_mail_content = utils.http_get(url=mail_content_url)
                if individual_mail_content is None:
                    individual_mail_content = ""
                    logger.warning(f"Failed to fetch content for mail ID {mail_id} from {mail_content_url}")
                
                # Parse sender_str into a dict if possible, or use as is for a simple key
                sender_dict = {sender_str: sender_str} # Simple representation

                messages.append(
                    Message(
                        id=mail_id,
                        sender=sender_dict,
                        to={account.address: account.address},
                        subject=email_data.get("subject", ""),
                        text=individual_mail_content,
                        html=individual_mail_content,
                    )
                )
        except json.JSONDecodeError as je:
            logger.error(f"[LinShiEmailError] JSON decode error for message list of {account.address}: {je}. Content: {content_str[:200]}...")
        except Exception as e:
            logger.error(f"[LinShiEmailError] Error processing messages for {account.address}: {e}", exc_info=True)
            
        return messages

    def delete_account(self, account: Account) -> bool:
        logger.info(f"[LinShiEmailInfo] LinShiEmail does not support account deletion via this API implementation for {account.address}.")
        return True # Original returned True


class MailTM(TemporaryMail):
    """a python wrapper for mail.tm web api, documented at https://api.mail.tm/"""

    def __init__(self) -> None:
        super().__init__()
        self.api_address = "https://api.mail.tm"
        self.auth_headers = {} # Store JWT token here

    def _decode_response_mailtm(self, response_bytes: bytes) -> Optional[Dict]:
        """Decodes response and parses JSON, for MailTM specific use."""
        decoded_str = ""
        try:
            # Mail.tm API typically doesn't gzip its JSON responses, but good to be robust
            try:
                decoded_str = gzip.decompress(response_bytes).decode("utf8")
            except (gzip.BadGzipFile, EOFError, TypeError):
                decoded_str = response_bytes.decode("utf8")
            return json.loads(decoded_str)
        except UnicodeDecodeError as ue:
            logger.error(f"MailTM: Unicode decode error: {ue}. Data: {response_bytes[:100]}...")
        except json.JSONDecodeError as je:
            logger.error(f"MailTM: JSON decode error: {je}. Data: {decoded_str[:200]}...")
        return None

    def get_domains_list(self) -> list:
        headers = {"Accept": "application/ld+json"}
        # utils.http_get is external. Assuming it handles retries and returns str.
        content_str = utils.http_get(url=f"{self.api_address}/domains?page=1", headers=headers)
        if not content_str:
            logger.error("[MailTMError] Failed to fetch domains list.")
            return []
        try:
            response_json = json.loads(content_str)
            return [item.get("domain", "") for item in response_json.get("hydra:member", []) if item.get("domain")]
        except json.JSONDecodeError as e:
            logger.error(f"[MailTMError] Failed to parse domains list JSON: {e}. Content: {content_str[:200]}...")
            return []

    def _make_account_request(self, endpoint: str, address: str, password: str, max_retries: int = 3) -> Dict:
        account_payload = {"address": address, "password": password}
        req_headers = {"Accept": "application/ld+json", "Content-Type": "application/json"}
        url = f"{self.api_address}/{endpoint}"
        
        try:
            data = json.dumps(account_payload).encode("UTF8")
        except TypeError as te:
            logger.error(f"MailTM _make_account_request: Failed to serialize payload: {te}")
            return {}

        for attempt in range(max_retries):
            try:
                request = urllib.request.Request(url=url, data=data, headers=req_headers, method="POST")
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
                
                if response and response.getcode() in [200, 201]: # 201 for account creation, 200 for token
                    response_json = self._decode_response_mailtm(response.read())
                    if response_json:
                        return response_json # Success
                else:
                    status = response.getcode() if response else "N/A"
                    body = response.read().decode('utf-8', errors='ignore') if response else ""
                    logger.warning(f"MailTM _make_account_request to {endpoint} failed with status {status} on attempt {attempt + 1}. Body: {body[:200]}")
            
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"MailTM _make_account_request to {endpoint}: network error on attempt {attempt + 1}/{max_retries}: {e}")
            except Exception as e:
                logger.error(f"MailTM _make_account_request to {endpoint}: unexpected error on attempt {attempt + 1}/{max_retries}: {e}", exc_info=True)

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        logger.error(f"MailTM _make_account_request to {endpoint}: failed after {max_retries} attempts for address {address}.")
        return {}

    def _generate_jwt(self, address: str, password: str, max_retries: int = 3) -> bool:
        jwt_response = self._make_account_request(endpoint="token", address=address, password=password, max_retries=max_retries)
        if jwt_response and "token" in jwt_response:
            self.auth_headers = {
                "Accept": "application/ld+json", # As per API docs for /messages
                "Authorization": f"Bearer {jwt_response['token']}",
            }
            # Content-Type is not always needed for GET with auth header, but good to be clean.
            # self.auth_headers["Content-Type"] = "application/json" # If making POST/PUT with JWT
            return True
        
        logger.error(f"[MailTMError][JWTError] Failed to generate JWT token for {address}.")
        return False

    def get_account(self, max_retries: int = 3) -> Optional[Account]:
        address = self.generate_address(random.randint(6, 12))
        if not address:
            logger.error("[MailTMError] Failed to generate address for MailTM.")
            return None

        password = utils.random_chars(length=random.randint(8, 16), punctuation=True)
        response_json = self._make_account_request(endpoint="accounts", address=address, password=password, max_retries=max_retries)

        if response_json and "id" in response_json and "address" in response_json:
            account_id = response_json["id"]
            actual_address = response_json["address"] # API might normalize/confirm address
            
            if self._generate_jwt(actual_address, password, max_retries=max_retries):
                return Account(address=actual_address, password=password, id=account_id)
            else:
                # JWT generation failed, account might be created but unusable without token
                # Consider deleting the account if possible, or log inability to proceed
                logger.error(f"[MailTMError] Account created for {actual_address} but JWT generation failed. Account might be unusable.")
                # self.delete_account(Account(address=actual_address, id=account_id)) # Problem: delete needs JWT
                return None
        else:
            logger.error(f"[MailTMError] Failed to create temporary email with MailTM for {address}. Response: {response_json}")
            return None

    def get_messages(self, account: Account) -> list:
        if not account or not self.auth_headers or "Authorization" not in self.auth_headers:
            logger.warning(f"[MailTMError] Get messages called for {account.address} without valid auth (JWT).")
            return []

        # utils.http_get is external. Assuming it can take headers and returns str.
        messages_list_url = f"{self.api_address}/messages?page=1" # Get first page
        content_str = utils.http_get(url=messages_list_url, headers=self.auth_headers, retry=2)

        messages_out = []
        if not content_str:
            logger.warning(f"[MailTMError] No content received when listing messages for {account.address}.")
            return messages_out

        try:
            dataset_container = json.loads(content_str)
            message_items = dataset_container.get("hydra:member", [])
            
            for message_data in message_items:
                message_id = message_data.get("id")
                if not message_id:
                    logger.warning("[MailTMError] Message item found without an ID.")
                    continue

                # Fetch individual message details
                individual_message_url = f"{self.api_address}/messages/{message_id}"
                message_detail_str = utils.http_get(url=individual_message_url, headers=self.auth_headers)
                
                if not message_detail_str:
                    logger.warning(f"[MailTMError] Failed to fetch details for message ID {message_id} for {account.address}.")
                    continue

                try:
                    data = json.loads(message_detail_str)
                    text = data.get("text", "")
                    html = data.get("html", []) # API returns list of HTML strings or single string
                    html_content = html[0] if isinstance(html, list) and html else (html if isinstance(html, str) else "")

                    messages_out.append(
                        Message(
                            id=message_id,
                            sender=message_data.get("from"), # 'from' is a dict
                            to=message_data.get("to"),     # 'to' is a list of dicts
                            subject=message_data.get("subject", ""),
                            intro=message_data.get("intro", ""),
                            text=text,
                            html=html_content,
                            data=message_data, # Full message item from list view
                        )
                    )
                except json.JSONDecodeError as je_detail:
                    logger.error(f"[MailTMError] JSON decode error for message detail {message_id}: {je_detail}. Content: {message_detail_str[:200]}...")
        
        except json.JSONDecodeError as je_list:
            logger.error(f"[MailTMError] Failed to parse messages list for {account.address}: {je_list}. Content: {content_str[:200]}...")
        except Exception as e:
            logger.error(f"[MailTMError] Unexpected error listing messages for {account.address}: {e}", exc_info=True)
        
        return messages_out

    def delete_account(self, account: Account) -> bool:
        if not account or not account.id or not self.auth_headers or "Authorization" not in self.auth_headers:
            logger.warning(f"[MailTMError] Delete account called with invalid account object or missing auth for {getattr(account, 'address', 'N/A')}.")
            return False

        url = f"{self.api_address}/accounts/{account.id}"
        try:
            request = urllib.request.Request(url=url, headers=self.auth_headers, method="DELETE")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            # Successful deletion returns 204 No Content
            if response.getcode() == 204:
                logger.info(f"Successfully deleted MailTM account: {account.address}")
                return True
            else:
                logger.warning(f"[MailTMError] Delete account failed for {account.address}, status: {response.getcode()}, body: {response.read().decode('utf-8',errors='ignore')[:200]}")
                return False
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            logger.error(f"[MailTMError] Network error deleting account {account.address}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[MailTMError] Unexpected error deleting account {account.address}: {e}", exc_info=True)
        return False


class MOAKT(TemporaryMail):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> IO[bytes]:
            # This allows us to capture the 302 response itself, including headers like Set-Cookie
            return fp

    def __init__(self) -> None:
        super().__init__()
        # MOAKT uses language in path, e.g. /en, /zh. Sticking to /zh from original.
        self.base_url = "https://www.moakt.com" # Base URL
        self.api_address = f"{self.base_url}/zh"   # For display and reference
        self.session_headers = { # Store session-specific headers like cookies here
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br", # Server might send gzip
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.base_url, # Origin is usually without path
            "Referer": f"{self.base_url}/", # Referer might be base or language specific
            "User-Agent": utils.USER_AGENT,
        }

    def _decode_moakt_response(self, response_bytes: bytes) -> str:
        try:
            return gzip.decompress(response_bytes).decode("utf-8")
        except (gzip.BadGzipFile, TypeError, EOFError):
            try:
                return response_bytes.decode("utf-8", errors="replace")
            except UnicodeDecodeError as e:
                logger.warning(f"MOAKT: UTF-8 decode failed: {e}. Data: {response_bytes[:100]}")
                return ""
        except UnicodeDecodeError as e:
            logger.warning(f"MOAKT: UTF-8 decode failed after gzip: {e}.")
            return ""


    def get_domains_list(self) -> list:
        # Fetches domains from the main page.
        # This request should not require existing session cookies.
        initial_page_content = utils.http_get(url=self.api_address, headers=self.session_headers)
        if not initial_page_content:
            logger.error("[MOAKTError] Failed to fetch main page for domains.")
            return []
        try:
            return re.findall(r'<option\s+value="[^"]*">@([a-zA-Z0-9\.\-_]+)<\/option>', initial_page_content)
        except re.error as e:
            logger.error(f"[MOAKTError] Regex error parsing domains: {e}")
            return []

    def _make_account_request(self, username: str, domain: str, max_retries: int = 3) -> Optional[Account]:
        payload = {
            "domain": domain, # The actual selected domain like "@moakt.cc"
            "username": username,
            "preferred_domain": domain, # Seems redundant but present in web requests
            "setemail": "创建", # Value for "Create" button
        }
        
        # MOAKT inbox URL after creation, or where POST is made
        request_url = f"{self.api_address}/inbox" 
        
        # Headers for this specific request, copy from session and update Referer
        current_headers = self.session_headers.copy()
        current_headers["Referer"] = self.api_address # Referer is the page with the form

        for attempt in range(max_retries):
            try:
                # Data must be URL-encoded for Content-Type: application/x-www-form-urlencoded
                data = urllib.parse.urlencode(payload).encode('UTF8')
                
                opener = urllib.request.build_opener(self.NoRedirect) # Handle 302 manually
                request = urllib.request.Request(url=request_url, data=data, headers=current_headers, method="POST")
                response = opener.open(request, timeout=10) # context=utils.CTX if needed for SSL

                if response and response.getcode() in [200, 302]: # 302 means success (redirect to inbox)
                    # Capture Set-Cookie header to maintain session for subsequent get_messages
                    # MOAKT sets multiple cookies. Handle them carefully.
                    cookies = response.getheader("Set-Cookie")
                    if cookies:
                        # A simple append might not be robust for multiple Set-Cookie headers.
                        # For urllib, manual cookie management is tricky.
                        # A better way is to use http.cookiejar if complex cookie handling is needed.
                        # For now, assume the last Set-Cookie is or contains the session.
                        self.session_headers["Cookie"] = cookies # Overwrite/set cookie
                    
                    logger.info(f"MOAKT account {username}@{domain} request successful (status {response.getcode()}).")
                    return Account(address=f"{username}@{domain}")
                else:
                    status = response.getcode() if response else "N/A"
                    body = self._decode_moakt_response(response.read()) if response else ""
                    logger.warning(f"MOAKT _make_account_request for {username}@{domain} failed with status {status} on attempt {attempt + 1}. Body: {body[:200]}")

            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"MOAKT _make_account_request for {username}@{domain}: network error on attempt {attempt + 1}/{max_retries}: {e}")
            except Exception as e:
                logger.error(f"MOAKT _make_account_request for {username}@{domain}: unexpected error on attempt {attempt + 1}/{max_retries}: {e}", exc_info=True)

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        logger.error(f"MOAKT _make_account_request for {username}@{domain}: failed after {max_retries} attempts.")
        return None

    def get_account(self, max_retries: int = 3) -> Optional[Account]:
        address_str = self.generate_address(bits=random.randint(6, 12))
        if not address_str:
            logger.error("[MOAKTError] Failed to generate address string for MOAKT.")
            return None

        username, domain_part = address_str.split("@", maxsplit=1)
        # The domain from generate_address already has '@'. MOAKT form wants it without '@' for 'domain' field.
        # However, the select list options have '@domain.com'. Let's assume generate_address returns 'user@domain.com'
        # and the 'domain' field in payload should be '@domain.com'
        
        # Re-check domain format from get_domains_list. It returns 'domain.com', not '@domain.com'
        # So, when constructing payload, domain should be '@' + domain_part
        # payload["domain"] = f"@{domain_part}" 
        # The original code used domain_part directly, which could be an issue if moakt expects '@'.
        # Let's assume the domains from get_domains_list are what MOAKT's form uses in the <option value="...">
        # The payload 'domain' field is likely the value from one of those options.
        
        return self._make_account_request(username=username, domain=f"@{domain_part}", max_retries=max_retries)


    def get_messages(self, account: Account) -> list:
        if not account or "Cookie" not in self.session_headers: # Need session cookie
            logger.warning(f"[MOAKTError] Get messages for {getattr(account, 'address', 'N/A')} called without session cookie.")
            return []

        messages_out = []
        # URL to the inbox page (assuming session cookie navigates to correct inbox)
        inbox_url = f"{self.api_address}/inbox"
        
        # Use session_headers which should contain the cookie
        # utils.http_get is external, assume it uses provided headers.
        content_html = utils.http_get(url=inbox_url, headers=self.session_headers)
        if not content_html:
            logger.warning(f"[MOAKTError] Failed to fetch inbox content for {account.address}.")
            return messages_out

        try:
            # Regex to find links to individual emails: <a href="/zh/email/...">
            # Ensure it captures the path correctly relative to self.base_url
            mail_links = re.findall(r'<a\s+href="(/zh/email/[a-z0-9\-]+)">', content_html)
            if not mail_links:
                logger.info(f"No messages found in inbox for {account.address} via regex.")
                return messages_out

            for mail_path in mail_links:
                # MOAKT loads message content into a div, often from a specific "content" URL.
                # The original regex was correct to find the mail detail page link.
                # Then it appends "/content/" to get the raw HTML content of the email.
                mail_content_url = f"{self.base_url}{mail_path}/content/"
                
                # Fetch individual mail content using session headers
                individual_mail_html = utils.http_get(url=mail_content_url, headers=self.session_headers)
                if individual_mail_html is None: # Check if http_get can return None
                    logger.warning(f"Failed to fetch content for mail at {mail_content_url}")
                    individual_mail_html = ""

                # For MOAKT, sender/subject might need to be parsed from the inbox_html or individual_mail_html if needed.
                # The current Message object is created with only text/html from the content page.
                messages_out.append(Message(text=individual_mail_html, html=individual_mail_html, to={account.address: account.address}))
        
        except re.error as e:
            logger.error(f"[MOAKTError] Regex error parsing inbox for {account.address}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[MOAKTError] Unexpected error processing messages for {account.address}: {e}", exc_info=True)
            
        return messages_out

    def delete_account(self, account: Account) -> bool:
        if not account:
            return False
        
        # MOAKT logout URL might clear the session
        logout_url = f"{self.api_address}/inbox/logout"
        # Perform a GET request to logout, using existing session headers
        logged_out_content = utils.http_get(url=logout_url, headers=self.session_headers)
        
        if logged_out_content is not None: # Check if http_get indicates success
            logger.info(f"MOAKT session logged out for {account.address}. Account effectively 'deleted' or session cleared.")
            # Clear local session cookies as well
            if "Cookie" in self.session_headers:
                del self.session_headers["Cookie"]
            return True
        else:
            logger.warning(f"MOAKT logout request for {account.address} might have failed.")
            return False


class Emailnator(TemporaryMail):
    def __init__(self, onlygmail: bool = False) -> None:
        super().__init__()
        self.api_address = "https://www.emailnator.com"
        self.only_gmail = onlygmail
        # Base headers, Cookie and X-XSRF-TOKEN will be added after _get_xsrf_token
        self.req_headers = { # Renamed to req_headers to distinguish from MailTM's auth_headers
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate", # Server may send gzipped
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": utils.USER_AGENT,
            "Content-Type": "application/json",
            "Origin": "https://www.emailnator.com",
            "Referer": "https://www.emailnator.com/",
        }

    def _decode_emailnator_response(self, response_bytes: bytes) -> str:
        try:
            return gzip.decompress(response_bytes).decode("utf8")
        except (gzip.BadGzipFile, TypeError, EOFError):
            try:
                return response_bytes.decode("utf8")
            except UnicodeDecodeError as e:
                logger.warning(f"Emailnator: UTF-8 decode failed: {e}. Data: {response_bytes[:100]}")
                return ""
        except UnicodeDecodeError as e:
            logger.warning(f"Emailnator: UTF-8 decode failed after gzip: {e}.")
            return ""

    def get_domains_list(self) -> list:
        # As per original code, these are somewhat fixed or hard to get dynamically for Emailnator
        # if self.only_gmail:
        # return ["gmail.com", "googlemail.com"] # if strictly only_gmail
        return ["gmail.com", "googlemail.com", "smartnator.com", "psnator.com", "tmpmailtor.com", "mydefipet.live"]

    def _get_xsrf_token(self, max_retries: int = 3) -> tuple[str, str]:
        """Fetches XSRF token and session cookies."""
        # Headers for this specific request (no prior Cookie/XSRF needed)
        token_fetch_headers = self.req_headers.copy() 
        # Ensure Content-Type is not sent for a GET request if it causes issues
        # token_fetch_headers.pop("Content-Type", None) # Usually fine for GET

        for attempt in range(max_retries):
            try:
                request = urllib.request.Request(url=self.api_address, headers=token_fetch_headers)
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

                raw_cookies = response.getheader("Set-Cookie")
                if raw_cookies:
                    xsrf_token_match = re.search(r"XSRF-TOKEN=([^;]+)", raw_cookies)
                    xsrf_token = urllib.parse.unquote(xsrf_token_match.group(1), encoding="utf8", errors="replace") if xsrf_token_match else ""
                    
                    # Combine relevant cookies for the 'Cookie' header string
                    # Original: (XSRF-TOKEN|gmailnator_session)=(.+?);
                    # A simpler approach might be to take all cookies, but let's stick to named ones if that's what the server expects.
                    cookie_parts = re.findall(r"(XSRF-TOKEN|gmailnator_session)=([^;]+)", raw_cookies)
                    cookies_str = "; ".join([f"{name}={value}" for name, value in cookie_parts]).strip()

                    if xsrf_token and cookies_str:
                        # Update instance headers for subsequent requests
                        self.req_headers["Cookie"] = cookies_str
                        self.req_headers["X-XSRF-TOKEN"] = xsrf_token
                        return cookies_str, xsrf_token
                
                logger.warning(f"Emailnator _get_xsrf_token: Could not extract cookies or XSRF token on attempt {attempt + 1}/{max_retries}. Raw cookies: {raw_cookies}")

            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"Emailnator _get_xsrf_token: network error on attempt {attempt + 1}/{max_retries}: {e}")
            except Exception as e:
                logger.error(f"Emailnator _get_xsrf_token: unexpected error on attempt {attempt + 1}/{max_retries}: {e}", exc_info=True)
            
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 2))
        
        logger.error(f"Emailnator _get_xsrf_token: failed to get token/cookies after {max_retries} attempts.")
        return "", ""


    def get_account(self, max_retries: int = 3) -> Optional[Account]:
        # _get_xsrf_token handles its own retries and updates self.req_headers
        _, xsrf_token_val = self._get_xsrf_token(max_retries=max_retries) 
        if not xsrf_token_val or "Cookie" not in self.req_headers: # Check if headers were set
            logger.error(f"[EmailnatorError] Cannot create account: failed to get cookies/XSRF token from {self.api_address}")
            return None

        url = f"{self.api_address}/generate-email"
        email_options = ["plusGmail", "dotGmail"] if self.only_gmail else ["domain", "plusGmail", "dotGmail", "googleMail"]
        payload = {"email": email_options}

        for attempt in range(max_retries):
            try:
                data = json.dumps(payload).encode("UTF8")
                # self.req_headers should now contain Cookie and X-XSRF-TOKEN
                request = urllib.request.Request(url, data=data, headers=self.req_headers, method="POST")
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
                
                if response.getcode() == 200:
                    response_content_bytes = response.read()
                    decoded_str = self._decode_emailnator_response(response_content_bytes)
                    if not decoded_str:
                        logger.error(f"[EmailnatorError] Generate-email returned empty/undecodable response for options {email_options}.")
                        # This might be a non-retryable server issue for these options.
                        return None 
                        
                    try:
                        response_json = json.loads(decoded_str)
                        emails = response_json.get("email", []) # Expects a list of email strings
                        if emails and isinstance(emails, list) and emails[0]:
                            return Account(emails[0])
                        else:
                            logger.warning(f"[EmailnatorError] Account creation returned no emails or invalid format. Options: {email_options}, Response: {decoded_str[:200]}...")
                            return None # API success but no email, likely not retryable
                    except json.JSONDecodeError as je:
                        logger.error(f"[EmailnatorError] Failed to parse JSON from generate-email: {je}. Options: {email_options}, Response: {decoded_str[:200]}...")
                        return None # Parsing error, not retryable with same conditions
                else:
                    error_message = self._decode_emailnator_response(response.read())
                    logger.error(
                        f"[EmailnatorError] Cannot create email account, status {response.getcode()}, options: {email_options}, message: {error_message[:200]}..., attempt {attempt + 1}/{max_retries}"
                    )
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"[EmailnatorError] Network error during account creation (options: {email_options}, attempt {attempt + 1}/{max_retries}): {e}")
            except Exception as e:
                 logger.error(f"[EmailnatorError] Unexpected error during account creation (options: {email_options}, attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        logger.error(f"[EmailnatorError] Failed to create Emailnator account after {max_retries} attempts (options: {email_options}).")
        return None

    def _get_raw_messages_data(self, address: str, messageid: str = "", max_retries: int = 3) -> str:
        """Helper to fetch raw message list or specific message content."""
        if not address:
            logger.error(f"[EmailnatorError] _get_raw_messages_data: address is empty. Domain: {self.api_address}")
            return ""
        
        # Ensure XSRF token and cookie are available from a previous get_account or _get_xsrf_token call
        if "Cookie" not in self.req_headers or "X-XSRF-TOKEN" not in self.req_headers:
            logger.warning("[EmailnatorError] _get_raw_messages_data: XSRF token/cookie not in headers. Attempting to refresh.")
            _, token = self._get_xsrf_token(max_retries=1) # Try to refresh once
            if not token:
                logger.error("[EmailnatorError] Failed to refresh token/cookie for _get_raw_messages_data.")
                return ""


        url = f"{self.api_address}/message-list"
        payload = {"email": address}
        if not utils.isblank(messageid): # Assuming utils.isblank checks for None or empty string
            payload["messageID"] = messageid
        
        for attempt in range(max_retries):
            try:
                data = json.dumps(payload).encode("UTF8")
                request = urllib.request.Request(url, data=data, headers=self.req_headers, method="POST")
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
                
                if response.getcode() == 200:
                    response_bytes = response.read()
                    return self._decode_emailnator_response(response_bytes)
                else:
                    error_body = self._decode_emailnator_response(response.read())
                    logger.warning(f"[EmailnatorError] Failed to get messages data (status {response.getcode()}), attempt {attempt + 1}/{max_retries}. Email: {address}, MsgID: {messageid}. Body: {error_body[:200]}")
            
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                logger.warning(f"[EmailnatorError] Network error in _get_raw_messages_data (attempt {attempt + 1}/{max_retries}): {e}. Email: {address}, MsgID: {messageid}")
            except Exception as e:
                logger.error(f"[EmailnatorError] Unexpected error in _get_raw_messages_data (attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        logger.error(f"[EmailnatorError] Failed to get messages data for {address} (MsgID: {messageid}) after {max_retries} attempts.")
        return ""

    def get_messages(self, account: Account) -> list:
        if not account:
            return []
        
        messages_out = []
        try:
            # Get the list of messages first
            message_list_str = self._get_raw_messages_data(address=account.address)
            if not message_list_str:
                logger.warning(f"[EmailnatorError] No message list data received for {account.address}")
                return messages_out

            message_list_json = json.loads(message_list_str)
            message_items = message_list_json.get("messageData", [])
            
            for item_data in message_items:
                message_id_val = item_data.get("messageID", "")
                # Original code's check for ADs based on b64 encoding. Assuming utils.isb64encode is correct.
                if not message_id_val or not utils.isb64encode(content=message_id_val, padding=False):
                    logger.debug(f"Skipping message item, possibly an ad or invalid ID: {message_id_val}")
                    continue

                # Fetch the full content of this specific message
                individual_message_html = self._get_raw_messages_data(address=account.address, messageid=message_id_val)
                if not individual_message_html: # If fetching individual message fails
                    logger.warning(f"Failed to retrieve content for message ID {message_id_val} for {account.address}")
                    # Optionally, one could create a Message object with partial data from item_data
                    # For now, skip if full content isn't available.
                    continue

                sender_str = item_data.get("from", "")
                messages_out.append(
                    Message(
                        subject=item_data.get("subject", ""),
                        id=message_id_val,
                        sender={sender_str: sender_str}, # Simple representation
                        to={account.address: account.address},
                        html=individual_message_html, # This is the full HTML email body
                        text=individual_message_html, # Assuming text is same as HTML or parsed from it
                    )
                )
        except json.JSONDecodeError as je:
            logger.error(f"[EmailnatorError] JSON decode error processing messages for {account.address}: {je}. Data: {message_list_str[:200] if 'message_list_str' in locals() else 'N/A'}", exc_info=True)
        except Exception as e:
            logger.error(f"[EmailnatorError] Unexpected error in get_messages for {account.address}: {e}", exc_info=True)
            
        return messages_out

    def delete_account(self, account: Account) -> bool:
        logger.info(f"[EmailnatorInfo] Emailnator does not support account deletion via this API for {getattr(account, 'address', 'N/A')}.")
        return True # Original returns True


def create_instance(onlygmail: bool = False) -> Optional[TemporaryMail]:
    if onlygmail:
        try:
            logger.info("Creating Emailnator instance (Gmail only).")
            return Emailnator(onlygmail=True)
        except Exception as e:
            logger.error(f"Failed to instantiate Emailnator (Gmail only): {e}", exc_info=True)
            return None

    # List of available general-purpose provider classes/constructors
    # Use lambdas for constructors that take arguments
    providers = [
        RootSh,
        SnapMail,
        LinShiEmail,
        MailTM,
        MOAKT,
        lambda: Emailnator(onlygmail=False) 
    ]
    
    random.shuffle(providers) # Shuffle to try different providers

    for provider_factory in providers:
        provider_name = ""
        try:
            if hasattr(provider_factory, '__name__'): # It's a class
                provider_name = provider_factory.__name__
            else: # It's a lambda (for Emailnator)
                # Attempt to discern name for logging, a bit hacky
                # This introspection is limited for lambdas.
                provider_name = "Emailnator (general)" if "Emailnator" in str(provider_factory) else "UnknownLambdaProvider"

            logger.info(f"Attempting to create instance of {provider_name}.")
            instance = provider_factory()
            # Optionally, perform a quick check like get_domains_list here to ensure it's viable
            # For now, just successful instantiation is enough.
            logger.info(f"Successfully created instance of {provider_name}.")
            return instance
        except Exception as e:
            logger.error(f"Failed to instantiate provider {provider_name}: {e}", exc_info=True)
            # Try the next provider in the shuffled list
            continue
    
    logger.error("Failed to create an instance of any temporary mail provider.")
    return None
