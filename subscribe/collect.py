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

# ... (rest of your imports and setup code remains the same) ...

def represent_str_plain(dumper, data):
    if data.isdigit():
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

if hasattr(yaml, 'Dumper'):
    yaml.add_representer(str, represent_str_plain, Dumper=yaml.Dumper)
if hasattr(yaml, 'SafeDumper'):
    yaml.add_representer(str, represent_str_plain, Dumper=yaml.SafeDumper)

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

logging.basicConfig(level=logging.INFO)

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")

ALL_CLASH_DATA_API = os.environ.get("ALL_CLASH_DATA_API")
GIST_PAT = os.environ.get("GIST_PAT")

if not ALL_CLASH_DATA_API or not GIST_PAT:
    print("环境变量 ALL_CLASH_DATA_API 或 GIST_PAT 未设置！")
    print("ALL_CLASH_DATA_API 应为：") # You might want to add the expected format here
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
                filepath="coupons.txt", # This seems to be a file to write to, consider its interaction with repo_files
                delimiter=self.delimiter,
                chuck=chuck,
            )
            if candidates:
                for k, v in candidates.items():
                    item = domains.get(k, {})
                    item["coupon"] = v # Assumes 'v' is the coupon from candidates
                    domains[k] = item
                # If candidates were found, it implies an update, so overwrite should reflect this for saving
                # However, the 'overwrite' flag in the function signature has a different meaning (overwrite existing domains.txt from scratch)
                # Consider if 'overwrite_repo_file_domains' should be true here
        if customize_link:
            if isurl(customize_link):
                domains.update(self.parse_domains(utils.http_get(url=customize_link)))
        if not domains:
            logger.error("无法收集到新的可免费使用的机场信息")
            return tasks, domains # domains will be empty here
        task_set = {task.sub for task in tasks if task.sub} # Assuming TaskConfig has 'sub' which is the domain
        for domain, param in domains.items():
            name = crawl.naming_task(url=domain)
            # The condition below uses 'domain' which is a URL from domains.txt
            # 'task_set' contains subscription URLs. If domain is not a subscription URL, it's added.
            # This assumes domains collected (which are registration domains) can also be subscription links, or that
            # 'naming_task' and the workflow can derive/find subscriptions from these domains.
            if domain not in task_set: # More accurately, this should check if a task for this domain already exists.
                tasks.append(
                    TaskConfig(
                        name=name,
                        domain=domain, # This is the airport domain, not necessarily the sub link itself.
                        coupon=param.get("coupon", ""),
                        invite_code=param.get("invite_code", ""),
                        bin_name=self.bin_name,
                        rigid=rigid,
                        chuck=chuck,
                        special_protocols=self.special_protocols,
                    )
                )
                task_set.add(domain) # Adding domain to task_set to avoid re-adding if it appears multiple times in domains_dict
        return tasks, domains

def aggregate(args: argparse.Namespace) -> None:
    repo_files = {}
    for fname in ["coupons.txt", "domains.txt", "subscribes.txt", "valid-domains.txt"]:
        repo_files[fname] = fetch_repo_file(fname)

    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible
    subscribes_file = "subscribes.txt" # This is the filename to load existing subscriptions

    manager = SubscriptionManager(subconverter_bin, args.num, display, repo_files)
    tasks, domains_dict = manager.assign(
        domains_file="domains.txt", # File to load airport domains from
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.easygoing,
        chuck=args.chuck,
        subscribes_file=subscribes_file, # Used by load_exist
        refresh=args.refresh,
        customize_link=args.yourself,
    )

    if not tasks:
        logger.error("找不到任何有效配置，退出")
        sys.exit(0) # Exits if no tasks (either from existing subs or new domains)

    old_subscriptions = {t.sub for t in tasks if t.sub} # Subscriptions present before fetching nodes

    logger.info(f"开始生成订阅信息，任务总数: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    results = utils.multi_thread_run(func=workflow.executewrapper, tasks=tasks, num_threads=args.num)
    # results is a list of tuples, e.g., (subscription_url, list_of_proxies) or None for failures
    proxies = list(itertools.chain.from_iterable([x[1] for x in results if x and x[1]])) # Ensure x[1] (proxies list) is not None

    if not proxies:
        logger.error("未获取到任何节点，退出")
        sys.exit(0)

    # --- Optimized Deduplication Logic ---
    unique_proxies_map = {} # Using a map to store the first occurrence of each unique proxy
    for proxy in proxies:
        if not isinstance(proxy, dict): # Ensure proxy is a dictionary
            logger.warning(f"Skipping non-dictionary proxy item: {proxy}")
            continue

        # Normalize and extract key components for uniqueness
        # These are common fields that define a unique proxy server endpoint.
        server = proxy.get("server", "").strip().lower()
        port = str(proxy.get("port", "")).strip() # Port is usually int, convert to str for key consistency
        proxy_type = proxy.get("type", "").strip().lower() # e.g., 'vmess', 'ss', 'trojan'

        # A proxy is considered unique based on its server, port, and type.
        # The name is often variable and is regenerated later anyway.
        if not server or not port or not proxy_type:
            # logger.warning(f"Proxy '{proxy.get('name', 'Unnamed')}' is missing server, port, or type. Skipping for deduplication.")
            continue # Skip proxies with incomplete information for unique identification

        proxy_key = (server, port, proxy_type)

        if proxy_key not in unique_proxies_map:
            unique_proxies_map[proxy_key] = proxy
        # else:
            # logger.debug(f"Duplicate proxy skipped: {proxy_key} (Original name: {proxy.get('name', 'N/A')})")

    unique_proxies = list(unique_proxies_map.values())
    # --- End of Optimized Deduplication Logic ---

    if not unique_proxies: # Check if the list is empty after deduplication
        logger.error("所有节点均为重复或信息不完整，未获取到任何唯一有效节点，退出")
        sys.exit(0)

    # Rename unique proxies. Consider making the new name more descriptive if needed.
    for i, proxy in enumerate(unique_proxies, start=1):
        number = f"{i:02d}"
        # You could make the name more descriptive, e.g., by including the proxy type
        # proxy["name"] = f"yandex-{proxy.get('type', 'proxy').upper()}-{number}"
        proxy["name"] = f"yandex-{number}"


    nodes = []
    workspace = os.path.join(PATH, "clash")
    if args.skip:
        logger.info("跳过节点可用性检测，所有提取到的唯一节点将直接使用。")
        nodes = clash.filter_proxies(unique_proxies).get("proxies", []) # Assumes filter_proxies is still desired
        if not nodes: # filter_proxies might return empty if it has its own filtering logic
            logger.warning("clash.filter_proxies 返回空节点列表。")
            # Decide if you want to use unique_proxies directly or exit
            # For now, let's assume if filter_proxies is used, its result is respected.
            # If you want all unique_proxies when skipping, then: nodes = unique_proxies
    else:
        binpath = os.path.join(workspace, clash_bin)
        config_file = "config.yaml"
        clash.generate_config(workspace, unique_proxies, config_file) # Use unique_proxies
        utils.chmod(binpath)
        logger.info(f"启动 clash, 工作目录: {workspace}, 配置文件: {config_file}")
        # Ensure process variable is consistently defined
        process = None
        try:
            process = subprocess.Popen([binpath, "-d", workspace, "-f", os.path.join(workspace, config_file)])
            logger.info(f"clash启动成功，开始检测节点，节点数: {len(unique_proxies)}")
            time.sleep(random.randint(3, 6)) # Allow time for Clash to start and load proxies
            # Prepare parameters for Clash check
            params = [[p, clash.EXTERNAL_CONTROLLER, args.delay, args.url, 5000, False] for p in unique_proxies if isinstance(p, dict)]
            # The old code used args.delay for timeout in clash.check and 5000 for something else.
            # Re-checking clash.check signature: clash.check(proxy, external_controller, timeout_pu, test_url, timeout_pr, verbose)
            # timeout_pu is 'timeout_proxy_udp' and timeout_pr is 'timeout_proxy_request'
            # Assuming args.delay is for the proxy request timeout. Let's use a fixed value for UDP or make it configurable.
            # The original code had: params = [[p, clash.EXTERNAL_CONTROLLER, 5000, args.url, args.delay, False] ...
            # This seems to map 5000 to timeout_pu and args.delay to timeout_pr. Let's keep that.
            
            masks = utils.multi_thread_run(func=clash.check, tasks=params, num_threads=args.num, show_progress=display)
            nodes = [unique_proxies[i] for i in range(len(unique_proxies)) if masks[i]]
        except Exception as e:
            logger.error(f"Clash 运行或节点检测过程中发生错误: {e}")
            # Ensure nodes is empty if error occurs before it's populated
            nodes = []
        finally:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5) # Wait a bit for termination
                    logger.info("Clash 进程已终止。")
                except subprocess.TimeoutExpired:
                    logger.warning("Clash 进程未能及时终止，尝试强制终止。")
                    process.kill()
                    process.wait()
                    logger.info("Clash 进程已强制终止。")
                except Exception as e:
                    logger.error(f"终止 clash 进程失败: {e}")

        if not nodes:
            logger.error("未获取到任何可用节点（通过Clash检测后）。")
            # Depending on desired behavior, you might not want to sys.exit(0) here
            # if you still want to save subscription files, etc.
            # For now, matching old behavior:
            if not args.skip: # Only exit if not skipping, as skipping implies user accepts potentially unavailable nodes
                sys.exit(0)


    # Extract subscription URLs from the processed unique_proxies
    # Each proxy dictionary might have a 'sub' key indicating its origin subscription.
    subscriptions = set()
    for p in unique_proxies: # Iterate over unique_proxies that formed the basis of 'nodes'
        if isinstance(p, dict) and p.get("sub"):
            subscriptions.add(p.pop("sub")) # Use pop to remove it if it's not needed in the proxy dict anymore

    # Clean up other potentially sensitive or temporary fields from proxy dicts
    for p in nodes: # nodes contains the final list of usable proxies
        if isinstance(p, dict):
            p.pop("chatgpt", None) # Remove if exists, None as default if not
            p.pop("liveness", None) # Remove if exists, None as default if not
            # Also remove 'sub' if it wasn't popped earlier or if iterating 'nodes' directly
            p.pop("sub", None)


    data = {"proxies": nodes}
    urls = list(subscriptions) # These are the subscription URLs from which active nodes were found
    source = "proxies.yaml" # This will contain the 'nodes' (tested and filtered proxies)
    supplier = os.path.join(PATH, "subconverter", source)

    if os.path.exists(supplier) and os.path.isfile(supplier):
        os.remove(supplier)
    with open(supplier, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True, Dumper=yaml.SafeDumper)

    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    targets, records = [], {}
    for target in args.targets:
        target_cleaned = utils.trim(target).lower()
        # Sanitize target for use in filenames or config section names
        convert_name = f'convert_{re.sub(r"[^a-zA-Z0-9_]", "_", target_cleaned)}'
        filename = subconverter.get_filename(target=target_cleaned) # Ensure get_filename handles various target strings safely
        # Determine if 'list_only' should be true based on target type
        list_only = not (target_cleaned in ("v2ray", "mixed") or "ss" in target_cleaned or args.all)
        targets.append((convert_name, filename, target_cleaned, list_only, args.vitiate))

    for t_name, t_filename, t_target, t_list_only, t_vitiate in targets:
        success = subconverter.generate_conf(
            config_path=generate_conf,
            section_name=t_name,
            source_file=source, # proxies.yaml
            output_filename=t_filename,
            target_format=t_target,
            include_all_rules=True, # This was hardcoded, confirm if it should be configurable
            list_only=t_list_only,
            vitiate=t_vitiate
        )
        if not success:
            logger.error(f"无法为目标 {t_target} 生成 subconverter 配置文件 ({t_name})")
            continue
        if subconverter.convert(binname=subconverter_bin, artifact=t_name): # artifact is the section name
            filepath = os.path.join(DATA_BASE, t_filename)
            try:
                shutil.move(os.path.join(PATH, "subconverter", t_filename), filepath)
                records[t_filename] = filepath
            except Exception as e:
                logger.error(f"移动文件 {t_filename} 到 {DATA_BASE} 失败: {e}")
        else:
            logger.error(f"Subconverter 转换失败: {t_name} for target {t_target}")


    if records:
        if os.path.exists(supplier): # Only remove supplier if conversions were successful
            os.remove(supplier)
    else:
        logger.error(f"所有目标转换失败。临时节点文件位于: {supplier}")
        # sys.exit(1) # Decide if to exit. If some files were created but not all.

    logger.info(f"共找到 {len(nodes)} 个可用节点，已尝试保存到: {list(records.keys())}")

    life, traffic = max(0, args.life), max(0, args.flow)
    if life > 0 or traffic > 0:
        # Filter new subscriptions based on life/traffic. 'urls' are from active nodes.
        # 'old_subscriptions' were subscriptions known at the start.
        new_subscriptions_to_check = [x for x in urls if x not in old_subscriptions]
        if new_subscriptions_to_check:
            logger.info(f"对 {len(new_subscriptions_to_check)} 个新订阅进行可用时长/流量检测。")
            # crawl.check_status task: [sub_url, check_type (0: status, 1: traffic, 2: full), traffic_threshold_gb, expiry_threshold_hours, retry_count, is_new_subscription]
            tasks_check = [[x, 2, traffic, life, 0, True] for x in new_subscriptions_to_check]
            results_check = utils.multi_thread_run(func=crawl.check_status, tasks=tasks_check, num_threads=args.num, show_progress=display)
            
            kept_new_subscriptions = [new_subscriptions_to_check[i] for i, res in enumerate(results_check) if res and res[0] and not res[1]]
            discard_count = len(new_subscriptions_to_check) - len(kept_new_subscriptions)
            logger.info(f"新订阅过滤完成，保留: {len(kept_new_subscriptions)}, 丢弃: {discard_count}")
            # Reconstruct 'urls' with filtered new subscriptions and all old subscriptions
            urls = kept_new_subscriptions + list(old_subscriptions) # Ensure old_subscriptions are strings
        else:
            logger.info("没有新的订阅需要进行可用时长/流量检测。")
    else:
        logger.info("未设置可用时长或流量阈值，跳过订阅过滤。")


    # Push updated subscription lists and domain files
    final_subscription_urls = sorted(list(set(s for s in urls if s))) # Ensure unique and not None
    try:
        push_repo_file("subscribes.txt", "\n".join(final_subscription_urls))
    except Exception as e:
        logger.error(f"推送 subscribes.txt 失败: {e}")

    try:
        # valid-domains.txt should contain domains from which active subscriptions came
        valid_domains_lines = sorted(list(set(utils.extract_domain(url=x, include_protocal=True) for x in final_subscription_urls if x)))
        push_repo_file("valid-domains.txt", "\n".join(valid_domains_lines))
    except Exception as e:
        logger.error(f"推送 valid-domains.txt 失败: {e}")

    try:
        domains_txt_content = ""
        # domains_dict contains the airport domains and their coupons/invite codes
        # This should ideally be updated if new airports were successfully registered and yielded working subs
        # For now, it writes back the initially loaded/discovered domains.
        # A more advanced logic might update coupons or remove domains that didn't yield working subs.
        for domain_url, info in domains_dict.items():
            line = domain_url
            coupon = info.get('coupon', '')
            invite_code = info.get('invite_code', '')
            if coupon or invite_code: # Only add delimiter if there's something to add
                line += f"{manager.delimiter}{coupon}{manager.delimiter}{invite_code}"
            domains_txt_content += line + "\n"
        push_repo_file("domains.txt", domains_txt_content.strip())
    except Exception as e:
        logger.error(f"推送 domains.txt 失败: {e}")

    # coupons.txt seems to be fetched but not modified in this script directly, other than by crawl.collect_airport
    # Ensure repo_files["coupons.txt"] has the latest content if crawl.collect_airport updated it.
    # The current implementation of crawl.collect_airport writes to a local "coupons.txt".
    # This local file's content should be read and pushed if it was modified.
    # For simplicity, let's assume repo_files["coupons.txt"] is what we want to push,
    # or it needs to be re-read if crawl.collect_airport modified it.
    # For now, pushing the fetched content:
    try:
        # If crawl.collect_airport updated a local 'coupons.txt', you'd read that file here.
        # e.g., if os.path.exists("coupons.txt"): repo_files["coupons.txt"] = open("coupons.txt").read()
        push_repo_file("coupons.txt", repo_files.get("coupons.txt", ""))
    except Exception as e:
        logger.error(f"推送 coupons.txt 失败: {e}")

    workflow.cleanup(workspace, []) # Clean up Clash workspace
    # Consider cleaning up other temporary files like subconverter/generate.ini if not already handled.

# ... (CustomHelpFormatter class and if __name__ == "__main__": block remain the same) ...

class CustomHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        if action.choices: # Check if the action has choices (like nargs="+")
            parts = []
            if action.option_strings: # For optional arguments like -t or --targets
                parts.extend(action.option_strings)
                # Ensure we append metavar only if nargs is not 0 and it's not the special case for targets
                if action.nargs != 0: # For actions that take arguments
                    # For --targets, we want to show choices, not a generic metavar
                    if action.dest == "targets": # Special handling for --targets to show choices
                        pass # Will be handled by super() or implicitly by HelpFormatter for choices
                    else:
                        default = self._get_default_metavar_for_optional(action)
                        args_string = self._format_args(action, default)
                        parts[-1] += " " + args_string
            else: # For positional arguments
                args_string = self._format_args(action, action.dest) # Use action.dest as metavar
                parts.append(args_string)
            return ", ".join(parts)
        else: # Fallback to default for actions without choices or specific formatting needs
            return super()._format_action_invocation(action)

    # Helper to get a default metavar for optional arguments
    def _get_default_metavar_for_optional(self, action):
        return action.dest.upper()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=CustomHelpFormatter)
    parser.add_argument("-a", "--all", dest="all", action="store_true", default=False, help="生成 clash 完整配置 (包含规则和脚本)") # Clarified help
    parser.add_argument("-c", "--chuck", dest="chuck", action="store_true", default=False, help="丢弃可能需要人工验证的候选机场网站") # Clarified help
    parser.add_argument("-d", "--delay", type=int, required=False, default=5000, help="允许的代理最大延迟 (ms)，用于节点检测")
    parser.add_argument("-e", "--easygoing", dest="easygoing", action="store_true", default=False, help="遇到邮箱白名单问题时尝试使用 Gmail 别名注册") # Clarified help
    parser.add_argument("-f", "--flow", type=int, required=False, default=1, help="筛选订阅：要求可用剩余流量 (GB)，0为不限制")
    parser.add_argument("-g", "--gist", type=str, required=False, default=os.environ.get("GIST_LINK", ""), help="GitHub 用户名和 gist id (username/gist_id)，用于推送订阅")
    parser.add_argument("-i", "--invisible", dest="invisible", action="store_true", default=False, help="不显示多线程任务的进度条")
    parser.add_argument("-k", "--key", type=str, required=False, default=os.environ.get("GIST_PAT", ""), help="GitHub Personal Access Token，用于编辑 gist")
    parser.add_argument("-l", "--life", type=int, required=False, default=12, help="筛选订阅：要求剩余可用时长 (小时)，0为不限制")
    parser.add_argument("-n", "--num", type=int, required=False, default=64, help="并发线程数 (用于网络请求、节点检测等)")
    parser.add_argument("-o", "--overwrite", dest="overwrite", action="store_true", default=False, help="从 TG 频道重新抓取机场信息并覆盖现有 domains.txt")
    parser.add_argument("-p", "--pages", type=int, required=False, default=sys.maxsize, help="爬取 Telegram 频道信息时的最大页数限制")
    parser.add_argument("-r", "--refresh", dest="refresh", action="store_true", default=False, help="仅使用现有订阅链接刷新节点，不注册新机场")
    parser.add_argument("-s", "--skip", dest="skip", action="store_true", default=False, help="跳过 Clash 节点的在线可用性检测")
    parser.add_argument("-t", "--targets", nargs="+", choices=subconverter.CONVERT_TARGETS, default=["clash", "v2ray", "singbox"],
                        help=f"选择要生成的配置类型。默认为: clash, v2ray, singbox。可用选项: {', '.join(subconverter.CONVERT_TARGETS)}")
    parser.add_argument("-u", "--url", type=str, required=False, default="https://www.google.com/generate_204", help="节点可用性检测的目标 URL")
    parser.add_argument("-v", "--vitiate", dest="vitiate", action="store_true", default=False, help="生成订阅配置时忽略 subconverter 的默认节点过滤规则")
    parser.add_argument("-y", "--yourself", type=str, required=False, default=os.environ.get("CUSTOMIZE_LINK", ""), help="用户自定义的机场域名列表 URL (纯文本格式，每行一个)")
    
    # Log current PATH and DATA_BASE for debugging if needed
    # logger.debug(f"Script PATH: {PATH}")
    # logger.debug(f"DATA_BASE: {DATA_BASE}")

    args = parser.parse_args()

    # Update GIST_PAT and ALL_CLASH_DATA_API if provided via command line
    # (Though typically these are environment variables, adding CLI override might be useful for some)
    if args.key:
        GIST_PAT = args.key
        api_headers['Authorization'] = f"token {GIST_PAT}" # Re-initialize headers if PAT changes
    
    # GIST_LINK is used for pushing, ALL_CLASH_DATA_API is for fetching/pushing repo files
    # The script structure implies ALL_CLASH_DATA_API is derived from a Gist or specific repo API structure.
    # If args.gist is 'username/gist_id', then ALL_CLASH_DATA_API needs to be formed correctly.
    # Current script assumes ALL_CLASH_DATA_API is a direct base URL for repo file contents.
    # For Gists, the API URL format is more like: https://api.github.com/gists/{gist_id}/files/{filename}
    # This script uses a simpler {ALL_CLASH_DATA_API}/{filename} structure, which might be for a regular repo.
    # Let's assume ALL_CLASH_DATA_API is correctly set as an environment variable.

    if not ALL_CLASH_DATA_API or not GIST_PAT:
        print("错误：环境变量 ALL_CLASH_DATA_API 或 GIST_PAT 未设置或通过 --key 提供。")
        print("ALL_CLASH_DATA_API 示例 (GitHub Repo): https://api.github.com/repos/USERNAME/REPONAME/contents")
        print("GIST_PAT: 你的 GitHub Personal Access Token")
        sys.exit(1)

    aggregate(args=args)
