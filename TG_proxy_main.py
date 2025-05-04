# coding=utf-8
import base64
import requests
import re
import time
import os
import random
import string
import datetime
from time import sleep
import chardet

# 试用机场链接（已移除 https://xn--4gqu8thxjfje.com）
home_urls = (
    'https://37cdn.ski9.cn',
    'http://vpn1.fengniaocloud.top',
    'http://vpn1.fnvpn.top',
    'https://abc.wisky.lat',
    'http://subuu.xfxvpn.me',
    'https://sub.juejie.store',
    'https://www.zygcloud.net',
    'https://www.zygcloud.com',
    'https://link.sunsun.icu',
    'http://vpn.bigbears.top',
    'http://daxiongyun.net',
    'https://liuliugoo.755r.cn',
    'https://by1.liuliugo.cfd',
    'https://by2.liuliugo.cfd',
    'https://sub.skrspc.org',
    'https://api.skrspc.org',
    'https://3by.liuliugo.cfd',
    'https://www.songbug.cloud',
    'https://dobcloud.com',
    'https://hn1r5k7322.bitmusttw.com',
    'http://uuvpn.me',
    'https://yun.dashiba.com',
    'https://5gsieutoc.fun',
    'https://app.1130.net',
    'https://panel.darkbaz.com',
    'https://full.kddi.best',
    'https://ikanned.com:12000',
    'https://apanel.allbatech.net',
    'https://abbabav2board.foxspirit.vip',
    'https://xunyungogogo.xyz',
    'https://www.kuaidianlianjienode.sbs',
    'https://20242024.dilala.xyz',
)

# 文件路径
update_path = "./sub/"
# 所有的节点明文信息
end_bas64 = []
# 永久订阅
e_sub = ['']
# 机场试用链接
try_sub = []
# 试用节点明文
end_try = []

def jiemi_base64(data):  # 解密base64
    decoded_bytes = base64.b64decode(data)
    encoding = chardet.detect(decoded_bytes)['encoding']
    decoded_str = decoded_bytes.decode(encoding)
    return decoded_str

# 写入文件
def write_document():
    if e_sub == [] or try_sub == []:
        print("订阅为空请检查！")
    else:
        random.shuffle(e_sub)
        for e in e_sub:
            try:
                res = requests.get(e)
                proxys = jiemi_base64(res.text)
                end_bas64.extend(proxys.splitlines())
            except:
                print(e, "永久订阅出现错误❌跳过")
        print('永久订阅更新完毕')
        random.shuffle(try_sub)
        for t in try_sub:
            try:
                res = requests.get(t)
                proxys = jiemi_base64(res.text)
                end_try.extend(proxys.splitlines())
            except Exception as er:
                print(t, "试用订阅出现错误❌跳过", er)
        print('试用订阅更新完毕', try_sub)
        end_bas64_A = list(set(end_bas64))
        print("去重完毕！！去除", len(end_bas64) - len(end_bas64_A), "个重复节点")
        bas64 = '\n'.join(end_bas64_A).replace('\n\n', "\n").replace('\n\n', "\n").replace('\n\n', "\n")
        bas64_try = '\n'.join(end_try).replace('\n\n', "\n").replace('\n\n', "\n").replace('\n\n', "\n")
        t = time.localtime()
        date = time.strftime('%y%m', t)
        date_day = time.strftime('%y%m%d', t)
        try:
            os.mkdir(f'{update_path}{date}')
        except FileExistsError:
            pass
        txt_dir = update_path + date + '/' + date_day + '.txt'
        file = open(txt_dir, 'w', encoding='utf-8')
        file.write(bas64)
        file.close()
        # 只保留总订阅写入
        obj = base64.b64encode(bas64.encode())
        plaintext_result = obj.decode()
        file_L = open("Long_term_subscription_num", 'w', encoding='utf-8')
        file_L.write(plaintext_result)
        obj_try = base64.b64encode(bas64_try.encode())
        plaintext_result_try = obj_try.decode()
        file_L_try = open("Long_term_subscription_try", 'w', encoding='utf-8')
        file_L_try.write(plaintext_result_try)
        print("合并完成✅")
        try:
            numbers = sum(1 for _ in open(txt_dir))
            print("共获取到", numbers, "节点")
        except:
            print("出现错误！")
    return

def get_sub_url():
    V2B_REG_REL_URL = '/api/v1/passport/auth/register'
    times = 1
    for current_url in home_urls:
        i = 0
        while i < times:
            header = {
                'Referer': current_url,
                'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            form_data = {
                'email': ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(12)) + '@gmail.com',
                'password': 'autosub_v2b',
                'invite_code': '',
                'email_code': ''
            }
            try:
                response = requests.post(
                    current_url + V2B_REG_REL_URL, data=form_data, headers=header)
                subscription_url = f'{current_url}/api/v1/client/subscribe?token={response.json()["data"]["token"]}'
                try_sub.append(subscription_url)
                e_sub.append(subscription_url)
                print("add:" + subscription_url)
            except Exception as e:
                print("获取订阅失败", e)
            i += 1

if __name__ == '__main__':
    print("========== 开始获取机场订阅链接 ==========")
    get_sub_url()
    print("========== 准备写入订阅 ==========")
    write_document()
    print("========== 写入完成任务结束 ==========")
