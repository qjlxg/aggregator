# -*- coding: utf-8 -*-
# https://github.com/awuaaaaa/vless-py
# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import itertools
import os
import random
import re
import shutil
import subprocess
import sys
import time
import yaml
from typing import List, Dict, Set, Tuple
from urllib.parse import urlparse

import crawl
import executable
import push
import utils
import workflow
import yaml
from airport import AirPort
from logger import logger
from urlvalidator import isurl
from workflow import TaskConfig

import clash
import subconverter

import geoip2.database

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")
MMDB_PATH = os.path.join(PATH, "clash", "Country.mmdb")

def get_flag_by_ip(ip: str, reader) -> str:
    try:
        response = reader.country(ip)
        country_code = response.country.iso_code
        if country_code:
            # 国旗表情生成
            return chr(0x1F1E6 + ord(country_code[0]) - ord('A')) + chr(0x1F1E6 + ord(country_code[1]) - ord('A'))
    except Exception:
        pass
    return "🏳️"

def assign(
    bin_name: str,
    domains_file: str = "",
    overwrite: bool = False,
    pages: int = sys.maxsize,
    rigid: bool = True,
    display: bool = True,
    num_threads: int = 0,
    **kwargs,
) -> List[TaskConfig]:
    def load_exist(filename: str) -> List[str]:
        if not filename:
            return []
        subscriptions: Set[str] = set()
        pattern = r"^https?:\/\/[^\s]+"
        local_file = os.path.join(DATA_BASE, filename)
        # 只从本地文件加载订阅，不再从git加载
        if os.path.exists(local_file) and os.path.isfile(local_file):
            with open(local_file, "r", encoding="utf8") as f:
                items = re.findall(pattern, str(f.read()), flags=re.M)
                subscriptions.update(items)
        logger.info("start checking whether existing subscriptions have expired")
        links = list(subscriptions)
        results = utils.multi_thread_run(
            func=crawl.check_status,
            tasks=links,
            num_threads=num_threads,
            show_progress=display,
        )
        return [links[i] for i in range(len(links)) if results[i][0] and not results[i][1]]

    def parse_domains(content: str) -> Dict[str, Dict[str, str]]:
        if not content or not isinstance(content, str):
            logger.warning("cannot found any domain due to content is empty or not string")
            return {}
        records: Dict[str, Dict[str, str]] = {}
        for line in content.split("\n"):
            line = utils.trim(line)
            if not line or line.startswith("#"):
                continue
            words = line.rsplit(delimiter, maxsplit=2)
            address = utils.trim(words[0])
            coupon = utils.trim(words[1]) if len(words) > 1 else ""
            invite_code = utils.trim(words[2]) if len(words) > 2 else ""
            records[address] = {"coupon": coupon, "invite_code": invite_code}
        return records

    subscribes_file = utils.trim(kwargs.get("subscribes_file", ""))
    chuck = kwargs.get("chuck", False)
    subscriptions = load_exist(subscribes_file)
    logger.info(f"load exists subscription finished, count: {len(subscriptions)}")
    special_protocols = AirPort.enable_special_protocols()
    tasks = (
        [
            TaskConfig(name=utils.random_chars(length=8), sub=x, bin_name=bin_name, special_protocols=special_protocols)
            for x in subscriptions
            if x
        ]
        if subscriptions
        else []
    )
    if tasks and kwargs.get("refresh", False):
        logger.info("skip registering new accounts, will use existing subscriptions for refreshing")
        return tasks
    domains, delimiter = {}, "@#@#"
    domains_file = utils.trim(domains_file) or "domains.txt"
    fullpath = os.path.join(DATA_BASE, domains_file)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        with open(fullpath, "r", encoding="UTF8") as f:
            domains.update(parse_domains(content=str(f.read())))
    if not domains or overwrite:
        candidates = crawl.collect_airport(
            channel="ji",
            page_num=pages,
            num_thread=num_threads,
            rigid=rigid,
            display=display,
            filepath=os.path.join(DATA_BASE, "coupons.txt"),
            delimiter=delimiter,
            chuck=chuck,
        )
        if candidates:
            for k, v in candidates.items():
                item = domains.get(k, {})
                item["coupon"] = v
                domains[k] = item
            overwrite = True
    customize_link = utils.trim(kwargs.get("customize_link", ""))
    if customize_link:
        if isurl(customize_link):
            domains.update(parse_domains(content=utils.http_get(url=customize_link)))
        else:
            local_file = os.path.join(DATA_BASE, customize_link)
            if local_file != fullpath and os.path.exists(local_file) and os.path.isfile(local_file):
                with open(local_file, "r", encoding="UTF8") as f:
                    domains.update(parse_domains(content=str(f.read())))
    if not domains:
        logger.error("cannot collect any new airport for free use")
        return tasks
    if overwrite:
        crawl.save_candidates(candidates=domains, filepath=fullpath, delimiter=delimiter)
    task_set: Set[str] = {task.sub for task in tasks if task.sub}
    for domain, param in domains.items():
        name = crawl.naming_task(url=domain)
        if domain not in task_set:
            tasks.append(
                TaskConfig(
                    name=name,
                    domain=domain,
                    coupon=param.get("coupon", ""),
                    invite_code=param.get("invite_code", ""),
                    bin_name=bin_name,
                    rigid=rigid,
                    chuck=chuck,
                    special_protocols=special_protocols,
                )
            )
            task_set.add(domain)
    return tasks

def aggregate(args: argparse.Namespace) -> None:
    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible
    subscribes_file = "subscribes.txt"
    access_token = utils.trim(args.key)
    # 不再从git加载订阅
    username, gist_id = "", ""
    tasks = assign(
        bin_name=subconverter_bin,
        domains_file="domains.txt",
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.easygoing,
        display=display,
        num_threads=args.num,
        refresh=args.refresh,
        chuck=args.chuck,
        username=username,
        gist_id=gist_id,
        access_token=access_token,
        subscribes_file=subscribes_file,
        customize_link=args.yourself,
    )
    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)
    old_subscriptions = {t.sub for t in tasks if t.sub}
    logger.info(f"start generate subscribes information, tasks: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)
    results = utils.multi_thread_run(func=workflow.executewrapper, tasks=tasks, num_threads=args.num)
    proxies = list(itertools.chain.from_iterable([x[1] for x in results if x]))
    if not proxies:
        logger.error("exit because cannot fetch any proxy node")
        sys.exit(0)
    # 代理节点去重
    unique_proxies: List[Dict] = []
    seen_proxies: Set[str] = set()
    for proxy in proxies:
        proxy_key = proxy.get("name", "") + proxy.get("server", "") + str(proxy.get("port", ""))
        if proxy_key and proxy_key not in seen_proxies:
            unique_proxies.append(proxy)
            seen_proxies.add(proxy_key)

    # ========== 只保留国旗+bing编号，自动补国旗 ==========
    reader = geoip2.database.Reader(MMDB_PATH)
    bing_counter = 1
    for proxy in unique_proxies:
        # 提取原有国旗
        name = proxy.get("name", "")
        # 匹配国旗表情
        flag_match = re.match(r"([\U0001F1E6-\U0001F1FF]{1,2})", name)
        flag = flag_match.group(1) if flag_match else ""
        # 如果没有国旗，尝试用IP查找
        if not flag:
            ip = proxy.get("server", "")
            flag = get_flag_by_ip(ip, reader)
        # 生成bing编号
        bing_name = f"bing-{bing_counter:03d}"
        proxy["name"] = f"{flag} {bing_name}"
        bing_counter += 1
    reader.close()
    # ========== 输出中文解释 ==========
    print("所有节点已重命名为：国旗+bing编号（如：🇬🇧 bing-001），其余字符全部用bing代替。若无国旗则自动根据IP补全。")

    nodes, workspace = [], os.path.join(PATH, "clash")
    if args.skip:
        nodes = clash.filter_proxies(unique_proxies).get("proxies", [])
    else:
        binpath = os.path.join(workspace, clash_bin)
        confif_file = "config.yaml"
        proxies_config = clash.generate_config(workspace, unique_proxies, confif_file)
        utils.chmod(binpath)
        logger.info(f"startup clash now, workspace: {workspace}, config: {confif_file}")
        process = subprocess.Popen([binpath, "-d", workspace, "-f", os.path.join(workspace, confif_file)])
        logger.info(f"clash start success, begin check proxies, num: {len(unique_proxies)}")
        time.sleep(random.randint(3, 6))
        params = [[p, clash.EXTERNAL_CONTROLLER, 5000, args.url, args.delay, False] for p in unique_proxies if isinstance(p, dict)]
        masks = utils.multi_thread_run(func=clash.check, tasks=params, num_threads=args.num, show_progress=display)
        try:
            process.terminate()
        except:
            logger.error("terminate clash process error")
        nodes = [unique_proxies[i] for i in range(len(unique_proxies)) if masks[i]]
        if not nodes:
            logger.error("cannot fetch any proxy")
            sys.exit(0)

    subscriptions: Set[str] = set()
    for p in unique_proxies:
        p.pop("chatgpt", False)
        p.pop("liveness", True)
        sub = p.pop("sub", "")
        if sub:
            subscriptions.add(sub)

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
        list_only = False if target == "v2ray" or target == "mixed" or "ss" in target else not args.all
        targets.append((convert_name, filename, target, list_only, args.vitiate))
    for t in targets:
        success = subconverter.generate_conf(generate_conf, t[0], source, t[1], t[2], True, t[3], t[4])
        if not success:
            logger.error(f"cannot generate subconverter config file for target: {t[2]}")
            continue
        if subconverter.convert(binname=subconverter_bin, artifact=t[0]):
            filepath = os.path.join(DATA_BASE, t[1])
            shutil.move(os.path.join(PATH, "subconverter", t[1]), filepath)
            records[t[1]] = filepath
    if records:
        os.remove(supplier)
    else:
        logger.error(f"all targets convert failed, you can view the temporary file: {supplier}")
        sys.exit(1)
    logger.info(f"found {len(nodes)} proxies, save it to {list(records.values())}")

    life, traffic = max(0, args.life), max(0, args.flow)
    if life > 0 or traffic > 0:
        new_subscriptions = [x for x in urls if x not in old_subscriptions]
        tasks = [[x, 2, traffic, life, 0, True] for x in new_subscriptions]
        results = utils.multi_thread_run(func=crawl.check_status, tasks=tasks, num_threads=args.num, show_progress=display)
        total = len(urls)
        urls = [new_subscriptions[i] for i in range(len(new_subscriptions)) if results[i][0] and not results[i][1]]
        discard = len(tasks) - len(urls)
        urls.extend(old_subscriptions)
        logger.info(f"filter subscriptions finished, total: {total}, found: {len(urls)}, discard: {discard}")

    # 保存去重后的订阅
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
    parser.add_argument("-a", "--all", dest="all", action="store_true", default=False, help="generate full configuration for clash")
    parser.add_argument("-c", "--chuck", dest="chuck", action="store_true", default=False, help="discard candidate sites that may require human-authentication")
    parser.add_argument("-d", "--delay", type=int, required=False, default=5000, help="proxies max delay allowed")
    parser.add_argument("-e", "--easygoing", dest="easygoing", action="store_true", default=False, help="try registering with a gmail alias when you encounter a whitelisted mailbox")
    parser.add_argument("-f", "--flow", type=int, required=False, default=0, help="remaining traffic available for use, unit: GB")
    parser.add_argument("-g", "--gist", type=str, required=False, default="", help="github username and gist id, separated by '/'")
    parser.add_argument("-i", "--invisible", dest="invisible", action="store_true", default=False, help="don't show check progress bar")
    parser.add_argument("-k", "--key", type=str, required=False, default="", help="github personal access token for editing gist")
    parser.add_argument("-l", "--life", type=int, required=False, default=0, help="remaining life time, unit: hours")
    parser.add_argument("-n", "--num", type=int, required=False, default=64, help="threads num for check proxy")
    parser.add_argument("-o", "--overwrite", dest="overwrite", action="store_true", default=False, help="overwrite domains")
    parser.add_argument("-p", "--pages", type=int, required=False, default=sys.maxsize, help="max page number when crawling telegram")
    parser.add_argument("-r", "--refresh", dest="refresh", action="store_true", default=False, help="refresh and remove expired proxies with existing subscriptions")
    parser.add_argument("-s", "--skip", dest="skip", action="store_true", default=False, help="skip usability checks")
    parser.add_argument("-t", "--targets", nargs="+", choices=subconverter.CONVERT_TARGETS, default=["clash", "v2ray", "singbox"], help=f"choose one or more generated profile type. default to clash, v2ray and singbox. supported: {subconverter.CONVERT_TARGETS}")
    parser.add_argument("-u", "--url", type=str, required=False, default="https://www.google.com/generate_204", help="test url")
    parser.add_argument("-v", "--vitiate", dest="vitiate", action="store_true", default=False, help="ignoring default proxies filter rules")
    parser.add_argument("-y", "--yourself", type=str, required=False, default="", help="the url to the list of airports that you maintain yourself")
    aggregate(args=parser.parse_args())
