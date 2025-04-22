

import requests
import base64
import json
import hashlib
import hmac
import random
import time
import pyaes
from urllib.parse import quote
from operator import itemgetter
from concurrent.futures import ThreadPoolExecutor, as_completed

session = requests.Session()
session.trust_env = False

def generate_nonce():
    return ''.join([str(random.randint(0, 9)) for _ in range(9)])

def generate_hmac_sha1_signature(key: str, message: str) -> str:
    key_bytes = bytes(key, 'utf-8')
    message_bytes = bytes(message, 'utf-8')
    sha1_hmac = hmac.new(key_bytes, message_bytes, hashlib.sha1).digest()
    return base64.b64encode(sha1_hmac).decode('utf-8')

def decrypt(b64str):
    cipher_bytes = base64.b64decode(b64str.encode())
    decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(b'k6NASqTxLWJ4cXF9kGRfl5Ltmiy0qGU1', cipher_bytes[:16]))
    return decrypter.feed(cipher_bytes[16:]) + decrypter.feed()

def fetch_ss():
    nonce = generate_nonce()
    ts = str(int(time.time()))
    message = f"h/hfX}}$ZDHcWH5rLpFdn=:x5D%Nh-gPOST/v3/choose_server/?nonce={nonce}&sid=h/hfX}}$ZDHcWH5rLpFdn=:x5D%Nh-g&ts={ts}&version=63"
    key = "G]n(/E5WdRz]:=:aq$46BA-$qjj3gZ"
    sign = generate_hmac_sha1_signature(key, message)
    data = {
        "version": 63,
        "nonce": nonce,
        "ts": ts,
        "sid": "h/hfX}$ZDHcWH5rLpFdn=:x5D%Nh-g",
        "sign": sign
    }
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2; ONEPLUS A5000 Build/NZH54D)',
        'Host': 'api.smallwings.cc',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }
    url = "http://api.smallwings.cc/api/v3/choose_server"
    transporter_list = []
    try:
        response = session.post(url, json=data, headers=headers)
        if response.status_code == 200:
            for node in response.json().get('data', []):
                ss = base64.b64decode(decrypt(node)).decode()[5:].split(':')
                ip = '.'.join(itemgetter(2, 8, 6, 10)(ss[3].split('.')))
                port = 0xffff - int(ss[0]) // 13
                transporter_list.append('ss://' + base64.b64encode(f'{ss[2]}:{ss[4]}'.encode()).decode() + f'@{ip}:{port}#' + quote(ss[1]))
            return transporter_list
        raise Exception(response.status_code)
    except Exception as e:
        print(f'获取节点失败: {e}')
    return transporter_list

print('正在获取节点:')
transporter_list = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(fetch_ss) for _ in range(50)]
    for future in as_completed(futures):
        for ss in future.result():
            if ss not in transporter_list:
                transporter_list.append(ss)

print('正在获取IP信息:')
if transporter_list:
    ip_list = [ss.split('@')[1].split(':')[0] for ss in transporter_list]
    response = session.post('http://ip-api.com/batch?fields=country,city', json=ip_list)
    if response.status_code == 200:
        info_list = response.json()
        if len(transporter_list) == len(info_list):
            for i in range(len(transporter_list)):
                transporter_list[i] = transporter_list[i].split('#')[0] + '#' + quote(f'{info_list[i]["country"]} {info_list[i]["city"]}')
        else:
            print(f'获取IP信息数量不相等\n节点数量: {len(transporter_list)}\nIP信息数量: {len(ip_list)}')
    else:
        print('获取IP信息失败', response.status_code)

print('\n'.join(transporter_list))
print('\n----------------\n')
print('节点数量:', len(transporter_list))

if transporter_list:
    with open('data/transporter.txt', 'w') as f:
        f.write('\n'.join(transporter_list))
        print('保存文件: transporter.txt')
