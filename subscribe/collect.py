# -*- coding: utf-8 -*-
# https://github.com/awuaaaaa/vless-py
# @Author  : wzdnzd（原始作者），优化及节点去重修改 by 优化者
# @Time    : 2022-07-15（原始时间）, 2025-05-05（优化时间）

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
# 加载 .env 文件中的环境变量或系统环境变量
load_dotenv()

# 定义项目根目录和 data 目录，本地文件存放位置
PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")

# 用于通过 GitHub API 获取私有仓库中 data 目录下文件的 API 地址
ALL_CLASH_DATA_API = os.environ.get("ALL_CLASH_DATA_API")  # 例如：https://api.github.com/repos/qjlxg/362/contents/data
GIST_PAT = os.environ.get("GIST_PAT")

# 配置用于私有仓库请求的请求头（Authorization 必须设置）
api_headers = {
    'User-Agent': 'Mozilla/5.0',
    'Authorization': f"token {GIST_PAT}"
}

def get_file_from_repo(filename: str) -> str:
    """
    获取私有仓库 data 目录下的指定文件，如果本地不存在则通过 GitHub API 下载到本地
    特殊文件 data/clash.yaml 不覆盖（直接返回本地路径）
    """
    # data/clash.yaml 保持输出目录不变
    if filename == "clash.yaml":
        return os.path.join(DATA_BASE, filename)
    local_path = os.path.join(DATA_BASE, filename)
    if not os.path.exists(local_path):
        # 拼接 API URL，例如：https://api.github.com/repos/qjlxg/362/contents/data/domains.txt?ref=main
        file_url = f"{ALL_CLASH_DATA_API}/{filename}?ref=main"
        r = requests.get(file_url, headers=api_headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "content" not in data:
            raise ValueError(f"未能在返回数据中找到 content 字段: {file_url}")
        # GitHub 返回的 content 是 base64 编码
        encoded = data["content"].replace("\n", "")
        decoded = base64.b64decode(encoded).decode("utf-8")
        os.makedirs(DATA_BASE, exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(decoded)
    return local_path

class SubscriptionManager:
    def __init__(self, bin_name: str, num_threads: int, display: bool):
        self.bin_name = bin_name
        self.num_threads = num_threads
        self.display = display
        self.delimiter = "@#@#"
        self.special_protocols = AirPort.enable_special_protocols()

    def load_exist(self, filename: str) -> List[str]:
        """只从本地文件加载订阅并去重、过滤失效"""
        if not filename:
            return []
        subscriptions: Set[str] = set()
        pattern = r"^https?:\/\/[^\s]+"
        local_file = os.path.join(DATA_BASE, filename)
        if os.path.exists(local_file) and os.path.isfile(local_file):
            with open(local_file, "r", encoding="utf8") as f:
                subscriptions.update(re.findall(pattern, f.read(), flags=re.M))
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
        """解析机场域名列表"""
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

    def assign(self, domains_file: str = "", overwrite: bool = False, pages: int = sys.maxsize, rigid: bool = True, chuck: bool = False, subscribes_file: str = "", refresh: bool = False, customize_link: str = "") -> List[TaskConfig]:
        subscriptions = self.load_exist(subscribes_file)
        logger.info(f"加载现有订阅完成，数量: {len(subscriptions)}")
        tasks = [
            TaskConfig(name=utils.random_chars(length=8), sub=x, bin_name=self.bin_name, special_protocols=self.special_protocols)
            for x in subscriptions if x
        ] if subscriptions else []
        if tasks and refresh:
            logger.info("跳过注册新账号，将使用现有订阅刷新")
            return tasks
        domains_file = utils.trim(domains_file) or "domains.txt"
        # 修改：通过 get_file_from_repo 从私有仓库（data目录）获取文件
        try:
            fullpath = get_file_from_repo(domains_file)
            with open(fullpath, "r", encoding="UTF8") as f:
                domains = self.parse_domains(f.read())
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
                filepath=os.path.join(DATA_BASE, "coupons.txt"),
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
            else:
                local_file = os.path.join(DATA_BASE, customize_link)
                if local_file != fullpath and os.path.exists(local_file) and os.path.isfile(local_file):
                    with open(local_file, "r", encoding="UTF8") as f:
                        domains.update(self.parse_domains(f.read()))
        if not domains:
            logger.error("无法收集到新的可免费使用的机场信息")
            return tasks
        if overwrite:
            crawl.save_candidates(candidates=domains, filepath=fullpath, delimiter=self.delimiter)
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
        return tasks

def aggregate(args: argparse.Namespace) -> None:
    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible
    subscribes_file = "subscribes.txt"
    manager = SubscriptionManager(subconverter_bin, args.num, display)
    tasks = manager.assign(
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
    # 改进节点去重：对name、server、port字段去掉前后空格，统一为小写，再构造唯一标识
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
    os.makedirs(DATA_BASE, exist_ok=True)
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
    utils.write_file(filename=os.path.join(DATA_BASE, subscribes_file), lines=urls)
    domains = [utils.extract_domain(url=x, include_protocal=True) for x in urls]
    utils.write_file(filename=os.path.join(DATA_BASE, "valid-domains.txt"), lines=list(set(domains)))
    workflow.cleanup(workspace, [])

class CustomHelpFormatter(argparse.HelpFormatter):
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
