# -*- coding: utf-8 -*-
import argparse
import itertools
import os
import random
import re
import shutil
import subprocess
import sys
import time
from typing import List, Dict, Set
import base64
import logging
import requests
import yaml
import socket # 导入 socket 模块

import crawl
import executable
import push
import utils
import workflow
from airport import AirPort
from logger import logger
from urlvalidator import isurl
from workflow import TaskConfig
import clash
import subconverter
import geoip2.database  # 导入 geoip2 库

from dotenv import load_dotenv
load_dotenv()

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")

ALL_CLASH_DATA_API = os.environ.get("ALL_CLASH_DATA_API")
GIST_PAT = os.environ.get("GIST_PAT")

if not ALL_CLASH_DATA_API or not GIST_PAT:
    print("环境变量 ALL_CLASH_DATA_API 或 GIST_PAT 未设置！")
    print("ALL_CLASH_DATA_API 应为：https://api.github.com/repos/qjlxg/362/contents/data")
    sys.exit(1)

api_headers = {
    'User-Agent': 'Mozilla/5.0',
    'Authorization': f"token {GIST_PAT}"
}

def fetch_repo_file(filename):
    try:
        url = f"{ALL_CLASH_DATA_API}/{filename}?ref=main"
        resp = requests.get(url, headers=api_headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "content" not in data:
            logger.warning(f"{filename} 无 content 字段")
            return ""
        return base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
    except Exception as e:
        logger.error(f"读取 {filename} 失败: {e}")
        return ""

def push_repo_file(filename, content):
    try:
        url = f"{ALL_CLASH_DATA_API}/{filename}"
        sha = None
        try:
            resp = requests.get(url, headers=api_headers, timeout=10)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except Exception as e:
            logger.warning(f"获取 {filename} sha 失败: {e}")
        payload = {
            "message": f"Update {filename} via script",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha
        resp = requests.put(url, json=payload, headers=api_headers, timeout=10)
        resp.raise_for_status()
        logger.info(f"{filename} 已推送到仓库")
    except Exception as e:
        logger.error(f"推送 {filename} 到仓库失败: {e}")

class SubscriptionManager:
    def __init__(self, bin_name: str, num_threads: int, display: bool, repo_files: dict):
        self.bin_name = bin_name
        self.num_threads = num_threads
        self.display = display
        self.delimiter = "@#@#"
        self.special_protocols = AirPort.enable_special_protocols()
        self.repo_files = repo_files

    def load_exist(self, filename: str) -> List[str]:
        if not filename or filename not in self.repo_files:
            return []
        subscriptions: Set[str] = set()
        pattern = r"^https?:\/\/[^\s]+"
        content = self.repo_files.get(filename, "")
        subscriptions.update(re.findall(pattern, content, flags=re.M))
        logger.info("开始校验现有订阅是否失效")
        links = list(subscriptions)
        results = utils.multi_thread_run(
            func=crawl.check_status,
            tasks=links,
            num_threads=self.num_threads,
            show_progress=self.display,
        )
        return [links[i] for i in range(len(links)) if results[i][0] and not results[i][1]]

    def parse_domains(self, content: str) -> Dict[str, Dict[str, str]]:
        if not content or not isinstance(content, str):
            logger.warning("内容为空或非字符串，无法解析域名")
            return {}
        records = {}
        for line in content.split("\n"):
            line = utils.trim(line)
            if not line or line.startswith("#"):
                continue
            words = line.rsplit(self.delimiter, maxsplit=2)
            address = utils.trim(words[0])
            coupon = utils.trim(words[1]) if len(words) > 1 else ""
            invite_code = utils.trim(words[2]) if len(words) > 2 else ""
            records[address] = {"coupon": coupon, "invite_code": invite_code}
        return records

    def assign(self, domains_file: str = "", overwrite: bool = False, pages: int = sys.maxsize, rigid: bool = True, chuck: bool = False, subscribes_file: str = "", refresh: bool = False, customize_link: str = "") -> (List[TaskConfig], dict):
        subscriptions = self.load_exist(subscribes_file)
        logger.info(f"加载现有订阅完成，数量: {len(subscriptions)}")
        tasks = [
            TaskConfig(name=utils.random_chars(length=8), sub=x, bin_name=self.bin_name, special_protocols=self.special_protocols)
            for x in subscriptions if x
        ] if subscriptions else []
        if tasks and refresh:
            logger.info("跳过注册新账号，将使用现有订阅刷新")
            return tasks, {}
        domains_file = utils.trim(domains_file) or "domains.txt"
        try:
            domains_content = self.repo_files.get(domains_file, "")
            domains = self.parse_domains(domains_content)
        except Exception as e:
            logger.error(f"读取 {domains_file} 失败: {e}")
            domains = {}
        if not domains or overwrite:
            candidates = crawl.collect_airport(
                channel="ji",
                page_num=pages,
                num_thread=self.num_threads,
                rigid=rigid,
                display=self.display,
                filepath="coupons.txt",
                delimiter=self.delimiter,
                chuck=chuck,
            )
            if candidates:
                for k, v in candidates.items():
                    item = domains.get(k, {})
                    item["coupon"] = v
                    domains[k] = item
                overwrite = True
        if customize_link:
            if isurl(customize_link):
                domains.update(self.parse_domains(utils.http_get(url=customize_link)))
        if not domains:
            logger.error("无法收集到新的可免费使用的机场信息")
            return tasks, domains
        task_set = {task.sub for task in tasks if task.sub}
        for domain, param in domains.items():
            name = crawl.naming_task(url=domain)
            if domain not in task_set:
                tasks.append(
                    TaskConfig(
                        name=name,
                        domain=domain,
                        coupon=param.get("coupon", ""),
                        invite_code=param.get("invite_code", ""),
                        bin_name=self.bin_name,
                        rigid=rigid,
                        chuck=chuck,
                        special_protocols=self.special_protocols,
                    )
                )
                task_set.add(domain)
        return tasks, domains

# 新增函数：根据 IP 获取国旗 emoji
def get_country_flag(ip):
    try:
        reader = geoip2.database.Reader(os.path.join(PATH, "clash", "Country.mmdb"))
        response = reader.country(ip)
        country_code = response.country.iso_code
        if country_code:
            flag = ''.join([chr(ord(char) + 127397) for char in country_code.upper()])
            return flag
        else:
            logger.warning(f"无法获取 IP {ip} 的国家代码")
            return ""
    except Exception as e:
        logger.warning(f"无法获取 IP {ip} 的国家信息: {e}")
        return ""

def aggregate(args: argparse.Namespace) -> None:
    repo_files = {}
    for fname in ["coupons.txt", "domains.txt", "subscribes.txt", "valid-domains.txt"]:
        repo_files[fname] = fetch_repo_file(fname)
    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible
    subscribes_file = "subscribes.txt"
    manager = SubscriptionManager(subconverter_bin, args.num, display, repo_files)
    tasks, domains_dict = manager.assign(
        domains_file="domains.txt",
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.easygoing,
        chuck=args.chuck,
        subscribes_file=subscribes_file,
        refresh=args.refresh,
        customize_link=args.yourself,
    )
    if not tasks:
        logger.error("找不到任何有效配置，退出")
        sys.exit(0)
    old_subscriptions = {t.sub for t in tasks if t.sub}
    logger.info(f"开始生成订阅信息，任务总数: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)
    results = utils.multi_thread_run(func=workflow.executewrapper, tasks=tasks, num_threads=args.num)
    proxies = list(itertools.chain.from_iterable([x[1] for x in results if x]))
    if not proxies:
        logger.error("未获取到任何节点，退出")
        sys.exit(0)
    unique_proxies = []
    seen_proxies = set()
    for proxy in proxies:
        name = proxy.get("name", "").strip().lower()
        server = proxy.get("server", "").strip().lower()
        port = str(proxy.get("port", "")).strip()
        proxy_key = f"{name}-{server}-{port}"
        if proxy_key and proxy_key not in seen_proxies:
            unique_proxies.append(proxy)
            seen_proxies.add(proxy_key)

    # 统一节点名称：保留国旗，替换为 yandex 并编号
    flag_counter = {}  # 每个国旗的编号计数器
    for proxy in unique_proxies:
        name = proxy.get("name", "")
        server = proxy.get("server", "")

        # 检查名称中是否包含国旗
        flag = ""
        for char in name:
            if ord(char) in range(127462, 127488):  # Unicode 国旗范围
                flag += char
            else:
                break  # 遇到非国旗字符停止

        # 如果没有国旗，通过 geoip2 生成
        if not flag and server:
            try:
                # 尝试将域名解析为 IP 地址
                ip_address = socket.gethostbyname(server)
                flag = get_country_flag(ip_address)
            except socket.gaierror as e:
                logger.warning(f"无法解析域名 {server}: {e}")
                flag = ""
            except Exception as e:
                logger.warning(f"获取{server}的国旗失败: {e}")
                flag = ""

        # 生成编号
        if flag:
            if flag not in flag_counter:
                flag_counter[flag] = 1
            else:
                flag_counter[flag] += 1
            number = f"{flag_counter[flag]:02d}"
            if name.startswith(flag):  # 如果 name 已经以国旗开头，则保留国旗
                proxy["name"] = f"{flag} yandex-{number}"
            else:
                proxy["name"] = f"{flag}yandex-{number}"  # 没有国旗开头则直接添加国旗
        else:
            # 如果无法获取国旗，使用默认编号
            number = f"{len(unique_proxies):02d}"
            proxy["name"] = f"yandex-{number}"

    nodes = []
    workspace = os.path.join(PATH, "clash")
    if args.skip:
        nodes = clash.filter_proxies(unique_proxies).get("proxies", [])
    else:
        binpath = os.path.join(workspace, clash_bin)
        config_file = "config.yaml"
        clash.generate_config(workspace, unique_proxies, config_file)
        utils.chmod(binpath)
        logger.info(f"启动 clash, 工作目录: {workspace}, 配置文件: {config_file}")
        process = subprocess.Popen([binpath, "-d", workspace, "-f", os.path.join(workspace, config_file)])
        logger.info(f"clash启动成功，开始检测节点，节点数: {len(unique_proxies)}")
        time.sleep(random.randint(3, 6))
        params = [[p, clash.EXTERNAL_CONTROLLER, 5000, args.url, args.delay, False] for p in unique_proxies if isinstance(p, dict)]
        masks = utils.multi_thread_run(func=clash.check, tasks=params, num_threads=args.num, show_progress=display)
        try:
            process.terminate()
        except Exception:
            logger.error("终止 clash 进程失败")
        nodes = [unique_proxies[i] for i in range(len(unique_proxies)) if masks[i]]
        if not nodes:
      


