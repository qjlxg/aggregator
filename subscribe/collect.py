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
import socket  # 导入 socket 模块
import geoip2.database  # 导入 geoip2 库

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

from dotenv import load_dotenv
load_dotenv()

# 设置日志级别
logging.basicConfig(level=logging.INFO)

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")

ALL_CLASH_DATA_API = os.environ.get("ALL_CLASH_DATA_API")
GIST_PAT = os.environ.get("GIST_PAT")

if not ALL_CLASH_DATA_API or not GIST_PAT:
    print("环境变量 ALL_CLASH_DATA_API 或 GIST_PAT 未设置！")
    print("ALL_CLASH_DATA_API 应为：")
    sys.exit(1)

api_headers = {
    'User-Agent': 'Mozilla/5.0',
    'Authorization': f"token {GIST_PAT}"
}

def fetch_repo_file(filename):
    """从 GitHub 仓库获取文件内容"""
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
    """推送文件内容到 GitHub 仓库"""
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
        """加载现有订阅并校验有效性"""
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
        """解析域名内容"""
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
        """分配任务并收集域名"""
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

def get_country_flag(server):
    """根据 server 获取国旗 emoji"""
    try:
        # 检查 server 是否为 IP 地址
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", server):
            ip = server
            logger.info(f"直接使用 IP 地址: {ip}")
        else:
            # 将域名解析为 IP 地址
            ip = socket.gethostbyname(server)
            logger.info(f"域名 {server} 解析为 IP: {ip}")
        
        # 查询国旗
        reader = geoip2.database.Reader(os.path.join(PATH, "clash", "Country.mmdb"))
        response = reader.country(ip)
        country_code = response.country.iso_code
        if country_code:
            flag = ''.join([chr(ord(char) + 127397) for char in country_code.upper()])
            logger.info(f"IP {ip} 的国旗: {flag}")
            return flag
        else:
            logger.warning(f"IP {ip} 无国家代码")
            return ""
    except socket.gaierror as e:
        logger.warning(f"域名解析失败 {server}: {e}")
        return ""
    except geoip2.errors.AddressNotFoundError:
        logger.warning(f"IP {ip} 在数据库中未找到")
        return ""
    except Exception as e:
        logger.warning(f"获取 {server} 的国旗失败: {e}")
        return ""

def aggregate(args: argparse.Namespace) -> None:
    """聚合订阅并生成配置文件"""
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

        # 如果没有国旗，尝试获取
        if not flag and server:
            flag = get_country_flag(server)

        # 生成编号
        if flag:
            if flag not in flag_counter:
                flag_counter[flag] = 1
            else:
                flag_counter[flag] += 1
            number = f"{flag_counter[flag]:02d}"
            proxy["name"] = f"{flag} yandex-{number}"
        else:
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
            logger.error("未获取到任何可用节点")
            sys.exit(0)
    subscriptions = {p.pop("sub", "") for p in unique_proxies if p.get("sub", "")}
    for p in unique_proxies:
        p.pop("chatgpt", False)
        p.pop("liveness", True)
    data = {"proxies": nodes}
    urls = list(subscriptions)
    source = "proxies.yaml"
    supplier = os.path.join(PATH, "subconverter", source)
    if os.path.exists(supplier) and os.path.isfile(supplier):
        os.remove(supplier)
    with open(supplier, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)
    targets, records = [], {}
    for target in args.targets:
        target = utils.trim(target).lower()
        convert_name = f'convert_{target.replace("&", "_").replace("=", "_")}'
        filename = subconverter.get_filename(target=target)
        list_only = False if target in ("v2ray", "mixed") or "ss" in target else not args.all
        targets.append((convert_name, filename, target, list_only, args.vitiate))
    for t in targets:
        success = subconverter.generate_conf(generate_conf, t[0], source, t[1], t[2], True, t[3], t[4])
        if not success:
            logger.error(f"无法为目标生成 subconverter 配置文件: {t[2]}")
            continue
        if subconverter.convert(binname=subconverter_bin, artifact=t[0]):
            filepath = os.path.join(DATA_BASE, t[1])
            shutil.move(os.path.join(PATH, "subconverter", t[1]), filepath)
            records[t[1]] = filepath
    if records:
        os.remove(supplier)
    else:
        logger.error(f"所有目标转换失败，可查看临时文件: {supplier}")
        sys.exit(1)
    logger.info(f"共找到 {len(nodes)} 个节点，已保存到 {list(records.values())}")
    life, traffic = max(0, args.life), max(0, args.flow)
    if life > 0 or traffic > 0:
        new_subscriptions = [x for x in urls if x not in old_subscriptions]
        tasks_check = [[x, 2, traffic, life, 0, True] for x in new_subscriptions]
        results = utils.multi_thread_run(func=crawl.check_status, tasks=tasks_check, num_threads=args.num, show_progress=display)
        total = len(urls)
        urls = [new_subscriptions[i] for i in range(len(new_subscriptions)) if results[i][0] and not results[i][1]]
        discard = len(tasks_check) - len(urls)
        urls.extend(old_subscriptions)
        logger.info(f"订阅过滤完成，总数: {total}, 保留: {len(urls)}, 丢弃: {discard}")

    try:
        push_repo_file("subscribes.txt", "\n".join(urls))
    except Exception as e:
        logger.error(f"推送 subscribes.txt 失败: {e}")
    try:
        domains_lines = [utils.extract_domain(url=x, include_protocal=True) for x in urls]
        push_repo_file("valid-domains.txt", "\n".join(list(set(domains_lines))))
    except Exception as e:
        logger.error(f"推送 valid-domains.txt 失败: {e}")
    try:
        domains_txt_content = ""
        for k, v in domains_dict.items():
            line = k
            if v.get("coupon") or v.get("invite_code"):
                line += f"{manager.delimiter}{v.get('coupon','')}{manager.delimiter}{v.get('invite_code','')}"
            domains_txt_content += line + "\n"
        push_repo_file("domains.txt", domains_txt_content.strip())
    except Exception as e:
        logger.error(f"推送 domains.txt 失败: {e}")
    try:
        push_repo_file("coupons.txt", repo_files.get("coupons.txt", ""))
    except Exception as e:
        logger.error(f"推送 coupons.txt 失败: {e}")

    workflow.cleanup(workspace, [])

class CustomHelpFormatter(argparse.HelpFormatter):
    """自定义帮助格式化器"""
    def _format_action_invocation(self, action):
        if action.choices:
            parts = []
            if action.option_strings:
                parts.extend(action.option_strings)
                if action.nargs != 0 and action.option_strings != ["-t", "--targets"]:
                    default = action.dest.upper()
                    args_string = self._format_args(action, default)
                    parts[-1] += " " + args_string
            else:
                args_string = self._format_args(action, action.dest)
                parts.append(args_string)
            return ", ".join(parts)
        else:
            return super()._format_action_invocation(action)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=CustomHelpFormatter)
    parser.add_argument("-a", "--all", dest="all", action="store_true", default=False, help="生成 clash 完整配置")
    parser.add_argument("-c", "--chuck", dest="chuck", action="store_true", default=False, help="丢弃可能需要人工验证的候选网站")
    parser.add_argument("-d", "--delay", type=int, required=False, default=5000, help="允许的代理最大延迟")
    parser.add_argument("-e", "--easygoing", dest="easygoing", action="store_true", default=False, help="遇到邮箱白名单问题时尝试使用 Gmail 别名")
    parser.add_argument("-f", "--flow", type=int, required=False, default=0, help="可用剩余流量，单位: GB")
    parser.add_argument("-g", "--gist", type=str, required=False, default=os.environ.get("GIST_LINK", ""), help="GitHub 用户名和 gist id，用 '/' 分隔")
    parser.add_argument("-i", "--invisible", dest="invisible", action="store_true", default=False, help="不显示检测进度条")
    parser.add_argument("-k", "--key", type=str, required=False, default=os.environ.get("GIST_PAT", ""), help="用于编辑 gist 的 GitHub personal access token")
    parser.add_argument("-l", "--life", type=int, required=False, default=0, help="剩余可用时长，单位: 小时")
    parser.add_argument("-n", "--num", type=int, required=False, default=64, help="检测代理使用的线程数")
    parser.add_argument("-o", "--overwrite", dest="overwrite", action="store_true", default=False, help="覆盖已存在的域名")
    parser.add_argument("-p", "--pages", type=int, required=False, default=sys.maxsize, help="爬取 Telegram 时的最大页数")
    parser.add_argument("-r", "--refresh", dest="refresh", action="store_true", default=False, help="使用现有订阅刷新并剔除过期节点")
    parser.add_argument("-s", "--skip", dest="skip", action="store_true", default=False, help="跳过可用性检测")
    parser.add_argument("-t", "--targets", nargs="+", choices=subconverter.CONVERT_TARGETS, default=["clash", "v2ray", "singbox"], help=f"选择要生成的配置类型，默认为 clash, v2ray 和 singbox，支持: {subconverter.CONVERT_TARGETS}")
    parser.add_argument("-u", "--url", type=str, required=False, default="https://www.google.com/generate_204", help="测试 URL")
    parser.add_argument("-v", "--vitiate", dest="vitiate", action="store_true", default=False, help="忽略默认代理过滤规则")
    parser.add_argument("-y", "--yourself", type=str, required=False, default=os.environ.get("CUSTOMIZE_LINK", ""), help="你维护的机场列表的 URL")
    aggregate(args=parser.parse_args())
