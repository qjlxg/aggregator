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

# Custom YAML representer to avoid quotes around plain strings (like numbers)
def represent_str_plain(dumper, data):
    if data.isdigit():
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

# Add the custom representer to YAML Dumper
if hasattr(yaml, 'Dumper'):
    yaml.add_representer(str, represent_str_plain, Dumper=yaml.Dumper)
if hasattr(yaml, 'SafeDumper'):
    yaml.add_representer(str, represent_str_plain, Dumper=yaml.SafeDumper)

# 导入项目内部模块
# 假设这些模块 (crawl, executable, push, utils, workflow, airport, logger, urlvalidator, clash, subconverter)
# 存在于与此脚本同级的目录结构中，并且提供了脚本所需的功能。
# 注意：clash 模块中的节点检测相关函数在此脚本中不再使用。
import crawl
import executable
import push
import utils
import workflow
from airport import AirPort
from logger import logger
from urlvalidator import isurl
from workflow import TaskConfig
# import clash # 不再需要 clash 模块进行节点检测
import subconverter

# Load environment variables from a .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO)

# Determine base path and data directory
PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_BASE = os.path.join(PATH, "data")

# Ensure data directory exists
if not os.path.exists(DATA_BASE):
    os.makedirs(DATA_BASE, exist_ok=True)

# Read environment variables for GitHub API and PAT
ALL_CLASH_DATA_API = os.environ.get("ALL_CLASH_DATA_API")
GIST_PAT = os.environ.get("GIST_PAT")

# Check if required environment variables are set
if not ALL_CLASH_DATA_API or not GIST_PAT:
    print("错误：环境变量 ALL_CLASH_DATA_API 或 GIST_PAT 未设置！")
    print("ALL_CLASH_DATA_API 应为 GitHub 仓库 API 地址，例如：https://api.github.com/repos/你的用户名/你的仓库名/contents")
    print("GIST_PAT 应为具有访问仓库权限的 GitHub Personal Access Token")
    sys.exit(1)

# Headers for GitHub API requests
api_headers = {
    'User-Agent': 'Mozilla/5.0',
    'Authorization': f"token {GIST_PAT}"
}

# Function to fetch a file's content from the configured GitHub repository
def fetch_repo_file(filename):
    """Fetches file content from the configured GitHub repository."""
    try:
        url = f"{ALL_CLASH_DATA_API}/{filename}?ref=main" # Assuming 'main' branch
        resp = requests.get(url, headers=api_headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "content" not in data:
            logger.warning(f"{filename} 无 content 字段")
            return ""
        # Decode base64 content
        return base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
    except Exception as e:
        logger.error(f"读取 {filename} 失败: {e}")
        return ""

# Function to push (create or update) a file to the configured GitHub repository
def push_repo_file(filename, content):
    """Pushes file content to the configured GitHub repository."""
    try:
        url = f"{ALL_CLASH_DATA_API}/{filename}"
        sha = None
        # Try to get the current SHA of the file if it exists (needed for updates)
        try:
            resp = requests.get(url, headers=api_headers, timeout=10)
            if resp.status_code == 200:
                sha = resp.json().get("sha")
        except Exception as e:
            logger.warning(f"获取 {filename} sha 失败: {e}")

        # Prepare the payload for the PUT request
        payload = {
            "message": f"Update {filename} via script",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main" # Assuming 'main' branch
        }
        if sha:
            payload["sha"] = sha # Include SHA if updating an existing file

        # Send the PUT request to update/create the file
        resp = requests.put(url, json=payload, headers=api_headers, timeout=10)
        resp.raise_for_status()
        logger.info(f"{filename} 已推送到仓库")
    except Exception as e:
        logger.error(f"推送 {filename} 到仓库失败: {e}")

# Class to manage subscriptions, including loading, parsing, and assigning tasks
class SubscriptionManager:
    def __init__(self, bin_name: str, num_threads: int, display: bool, repo_files: dict):
        self.bin_name = bin_name
        self.num_threads = num_threads
        self.display = display
        self.delimiter = "@#@#" # Delimiter used in domains.txt
        self.special_protocols = AirPort.enable_special_protocols() # Get special protocols from AirPort module
        self.repo_files = repo_files # Dictionary of file contents fetched from repo

    def load_exist(self, filename: str) -> List[str]:
        """Loads existing subscriptions from a file fetched from the repository and checks their status (basic check)."""
        if not filename or filename not in self.repo_files:
            logger.info(f"未找到仓库文件 {filename}，不加载现有订阅。")
            return []

        subscriptions: Set[str] = set()
        # Regex to find URLs starting with http or https
        pattern = r"^https?:\/\/[^\s]+"
        content = self.repo_files.get(filename, "")
        subscriptions.update(re.findall(pattern, content, flags=re.M))
        logger.info(f"从仓库文件 {filename} 加载到 {len(subscriptions)} 个现有订阅。")

        if not subscriptions:
            return []

        # 在没有节点检测的情况下，这里可以进行一个基本的 URL 可访问性检查，
        # 或者完全跳过检查，直接使用加载到的订阅。
        # 为了简化并去除节点检测，我们这里直接返回加载到的订阅。
        # 如果需要基本的 URL 可访问性检查，可以调用 utils.multi_thread_run 和 crawl.check_status，
        # 但要确保 check_status 不依赖于 Clash 或其他节点检测工具。
        logger.info("跳过现有订阅的可用性校验（节点检测功能已移除）。")
        return list(subscriptions)

    def parse_domains(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parses domain information (with coupon/invite code) from file content."""
        if not content or not isinstance(content, str):
            logger.warning("内容为空或非字符串，无法解析域名")
            return {}
        records = {}
        for line in content.split("\n"):
            line = utils.trim(line)
            if not line or line.startswith("#"): # Skip empty lines and comments
                continue
            # Split line by delimiter, allowing for missing coupon/invite code
            words = line.rsplit(self.delimiter, maxsplit=2)
            address = utils.trim(words[0])
            coupon = utils.trim(words[1]) if len(words) > 1 else ""
            invite_code = utils.trim(words[2]) if len(words) > 2 else ""
            if address:
                records[address] = {"coupon": coupon, "invite_code": invite_code}
        return records

    def assign(self, domains_file: str = "", overwrite: bool = False, pages: int = sys.maxsize, rigid: bool = True, chuck: bool = False, subscribes_file: str = "", refresh: bool = False, customize_link: str = "") -> (List[TaskConfig], dict):
        """Assigns tasks based on existing subscriptions and newly crawled domains."""
        # Load existing subscriptions
        subscriptions = self.load_exist(subscribes_file)
        logger.info(f"加载现有订阅完成，数量: {len(subscriptions)}")

        # Create tasks for existing subscriptions
        tasks = [
            TaskConfig(name=utils.random_chars(length=8), sub=x, bin_name=self.bin_name, special_protocols=self.special_protocols)
            for x in subscriptions if x
        ] if subscriptions else []

        # If refresh is requested and existing tasks exist, skip crawling new domains
        if tasks and refresh:
            logger.info("跳过注册新账号，将使用现有订阅刷新")
            return tasks, {}

        # Load existing domains from the specified file
        domains_file = utils.trim(domains_file) or "domains.txt"
        try:
            domains_content = self.repo_files.get(domains_file, "")
            domains = self.parse_domains(domains_content)
            logger.info(f"从仓库文件 {domains_file} 加载到 {len(domains)} 个域名信息。")
        except Exception as e:
            logger.error(f"读取 {domains_file} 失败: {e}")
            domains = {}

        # If domains are empty or overwrite is requested, crawl for new airports
        if not domains or overwrite:
            logger.info("开始收集新的机场信息...")
            candidates = crawl.collect_airport(
                channel="ji", # Channel to crawl (e.g., Telegram)
                page_num=pages, # Max pages to crawl
                num_thread=self.num_threads,
                rigid=rigid, # Whether to be rigid about email verification
                display=self.display,
                filepath="coupons.txt", # Filepath for coupons (not directly used here, but passed to crawl)
                delimiter=self.delimiter,
                chuck=chuck, # Whether to chuck domains requiring manual verification
            )
            if candidates:
                logger.info(f"收集到 {len(candidates)} 个新的机场候选。")
                # Merge new candidates with existing domains
                for k, v in candidates.items():
                    item = domains.get(k, {})
                    item["coupon"] = v # Assuming v is the coupon
                    domains[k] = item
                overwrite = True # Mark as overwritten if new candidates were found
            else:
                logger.warning("未收集到新的机场候选。")

        # If a customize link is provided, parse domains from that link
        if customize_link:
            logger.info(f"从自定义链接 {customize_link} 加载域名信息...")
            if isurl(customize_link):
                try:
                    custom_content = utils.http_get(url=customize_link)
                    domains.update(self.parse_domains(custom_content))
                    logger.info(f"从自定义链接加载到 {len(self.parse_domains(custom_content))} 个域名信息。")
                except Exception as e:
                    logger.error(f"从自定义链接 {customize_link} 加载域名失败: {e}")
            else:
                logger.warning(f"自定义链接格式无效: {customize_link}")


        if not domains:
            logger.error("无法收集到新的可免费使用的机场信息")
            return tasks, domains # Return existing tasks and empty domains if no domains found

        # Add new domains as tasks if they are not already present as subscriptions
        task_set = {task.sub for task in tasks if task.sub} # Set of existing subscription URLs
        for domain, param in domains.items():
            # For domains, we create a task to register and get a subscription
            if domain and domain not in task_set: # Avoid adding duplicate domains if they are already subscriptions
                name = crawl.naming_task(url=domain) # Generate a task name
                tasks.append(
                    TaskConfig(
                        name=name,
                        domain=domain, # This is a domain, not a direct subscription URL yet
                        coupon=param.get("coupon", ""),
                        invite_code=param.get("invite_code", ""),
                        bin_name=self.bin_name,
                        rigid=rigid,
                        chuck=chuck,
                        special_protocols=self.special_protocols,
                    )
                )
                # Note: We don't add the domain to task_set here, as it's not a subscription URL yet.
                # The actual subscription URL will be obtained during task execution.

        logger.info(f"总共生成 {len(tasks)} 个任务 (包括现有订阅和待注册域名)。")
        return tasks, domains # Return the list of tasks and the parsed domains dictionary

# Main aggregation function (without node checking)
def aggregate_no_check(args: argparse.Namespace) -> None:
    """Aggregates subscriptions, deduplicates nodes, and generates configuration files (without node checking)."""
    logger.info("开始聚合订阅 (跳过节点可用性检测)...")

    # Fetch required files from the repository
    repo_files = {}
    for fname in ["coupons.txt", "domains.txt", "subscribes.txt", "valid-domains.txt"]:
        repo_files[fname] = fetch_repo_file(fname)

    # Determine the path of subconverter executable
    # We don't need clash executable anymore
    _, subconverter_bin = executable.which_bin()
    if not subconverter_bin:
        logger.error("找不到 subconverter 可执行文件，请检查配置。")
        sys.exit(1)

    display = not args.invisible # Determine whether to show progress bars
    subscribes_file = "subscribes.txt" # File containing existing subscriptions

    # Initialize SubscriptionManager
    # Pass None for clash_bin as it's not used for detection
    manager = SubscriptionManager(subconverter_bin, args.num, display, repo_files)

    # Assign tasks (either from existing subscriptions or new domains)
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

    # Exit if no tasks were generated
    if not tasks:
        logger.error("找不到任何有效配置，退出")
        sys.exit(0)

    # Store old subscription URLs for later filtering
    old_subscriptions = {t.sub for t in tasks if t.sub}

    logger.info(f"开始执行任务生成订阅信息，任务总数: {len(tasks)}")

    # Clean up old subconverter generate.ini if it exists
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    # Execute tasks (crawl domains and get subscriptions, or process existing subs)
    # results format: [(task_name, [proxy1, proxy2, ...]), ...]
    results = utils.multi_thread_run(func=workflow.executewrapper, tasks=tasks, num_threads=args.num, show_progress=display)

    # Collect all proxies from task results
    proxies = list(itertools.chain.from_iterable([x[1] for x in results if x and x[1]]))

    # Exit if no proxies were obtained
    if not proxies:
        logger.error("未获取到任何节点，退出")
        sys.exit(0)

    # Deduplicate proxies based on name, server, and port
    unique_proxies = []
    seen_proxies = set()
    for proxy in proxies:
        # Ensure proxy is a dictionary and has required keys before accessing
        if not isinstance(proxy, dict):
            logger.warning(f"跳过无效代理对象: {proxy}")
            continue
        name = proxy.get("name", "").strip().lower()
        server = proxy.get("server", "").strip().lower()
        port = str(proxy.get("port", "")).strip() # Ensure port is string for key
        # Create a unique key for deduplication
        proxy_key = f"{name}-{server}-{port}"
        if proxy_key and proxy_key not in seen_proxies:
            unique_proxies.append(proxy)
            seen_proxies.add(proxy_key)

    logger.info(f"去重前节点数: {len(proxies)}, 去重后节点数: {len(unique_proxies)}")

    # --- 修正后的代码：过滤掉 password 字段包含 !<str> 的节点 ---
    # 定义要检查的特定标签和值前缀
    PROBLEM_PASSWORD_PREFIX = '!<str> '
    
    filtered_proxies = []
    discarded_count_password = 0
    for proxy in unique_proxies:
        # 检查 'password' 字段是否存在且其值为字符串
        if "password" in proxy and isinstance(proxy["password"], str):
            password_value = proxy["password"]
            # 如果 password 字段以 PROBLEM_PASSWORD_PREFIX 开头，则丢弃该节点
            if password_value.startswith(PROBLEM_PASSWORD_PREFIX):
                logger.warning(f"丢弃节点 '{proxy.get('name', '未知')}' (server: {proxy.get('server', '未知')}, port: {proxy.get('port', '未知')})，因其 'password' 字段包含 '{PROBLEM_PASSWORD_PREFIX}' 标签。原始值: '{password_value}'")
                discarded_count_password += 1
                continue # 跳过当前节点，不添加到 filtered_proxies
        filtered_proxies.append(proxy)

    unique_proxies = filtered_proxies # 更新 unique_proxies 为过滤后的列表
    logger.info(f"因 'password' 字段包含 '{PROBLEM_PASSWORD_PREFIX}' 而丢弃的节点数: {discarded_count_password}")
    logger.info(f"过滤掉含 '{PROBLEM_PASSWORD_PREFIX}' 密码的节点后，剩余节点数: {len(unique_proxies)}")
    # --- 结束修改 ---

    # Rename unique proxies sequentially (Optional, but keeps consistency)
    for i, proxy in enumerate(unique_proxies, start=1):
        number = f"{i:02d}"
        proxy["name"] = f"yandex-{number}" # Rename using a prefix and sequential number

    # --- Prepare Data for Output ---
    # In this version, nodes is simply the list of unique proxies
    nodes = unique_proxies

    # Extract subscription URLs from proxies that were successfully processed (they have a 'sub' key)
    # Note: This extracts subs from the *unique_proxies* list.
    subscriptions = {p.pop("sub", "") for p in unique_proxies if p.get("sub", "")}

    # Remove temporary/internal keys from proxy dictionaries before saving
    for p in unique_proxies:
        p.pop("chatgpt", False)
        p.pop("liveness", True)
        # Remove any other keys added during crawling/processing that shouldn't be in the final output

    # Data structure for the final YAML output
    data = {"proxies": nodes} # 'nodes' here is the list of unique_proxies

    # List of all collected subscription URLs (old and new)
    urls = list(subscriptions)

    # --- Generate and Save Final YAML ---
    # Define the final output file path
    final_output_filename = "clash.yaml"
    final_output_filepath = os.path.join(DATA_BASE, final_output_filename)

    # Save the final YAML data to the specified file
    try:
        with open(final_output_filepath, "w+", encoding="utf8") as f:
            yaml.dump(data, f, allow_unicode=True, Dumper=yaml.SafeDumper)
        logger.info(f"最终节点数据 (未检测可用性) 已保存至: {final_output_filepath}")
    except Exception as e:
        logger.error(f"保存最终节点数据到 {final_output_filepath} 失败: {e}")
        sys.exit(1) # Exit if saving the main output fails


    # Clean up old subconverter generate.ini again if it exists
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    # --- Generate Other Target Formats using Subconverter ---
    targets, records = [], {}
    # Prepare targets for subconverter based on command line arguments
    for target in args.targets:
        target = utils.trim(target).lower()
        convert_name = f'convert_{target.replace("&", "_").replace("=", "_")}'
        filename = subconverter.get_filename(target=target)
        # Determine if output should be list-only based on target and --all flag
        list_only = False if target in ("v2ray", "mixed") or "ss" in target else not args.all
        targets.append((convert_name, filename, target, list_only, args.vitiate))


    subconverter_source_filepath = final_output_filepath

    # Process each target format
    for t in targets:
        # Generate subconverter configuration for the target
        success = subconverter.generate_conf(generate_conf, t[0], subconverter_source_filepath, t[1], t[2], True, t[3], t[4])
        if not success:
            logger.error(f"无法为目标生成 subconverter 配置文件: {t[2]}")
            continue

        # Run subconverter to convert the source file to the target format
        if subconverter.convert(binname=subconverter_bin, artifact=t[0]):
            # Move the generated artifact to the data directory
            filepath = os.path.join(DATA_BASE, t[1])
            try:
                shutil.move(os.path.join(PATH, "subconverter", t[1]), filepath)
                records[t[1]] = filepath # Record the path of the generated file
                logger.info(f"生成目标文件 {t[1]} 并保存至 {filepath}")
            except Exception as e:
                logger.error(f"移动生成文件 {t[1]} 到 {filepath} 失败: {e}")
        else:
            logger.error(f"Subconverter 转换目标 {t[2]} 失败。")

    # Check if any target conversion was successful
    if not records:
        logger.error(f"所有目标转换失败。")

    logger.info(f"共收集到 {len(nodes)} 个去重后的节点。")
    if records:
        logger.info(f"生成的配置已保存至: {list(records.values())}")
    else:
        logger.warning("没有成功生成任何目标格式的配置文件。")


    # --- Subscription URL Filtering and Saving ---
    life, traffic = max(0, args.life), max(0, args.flow)
    if life > 0 or traffic > 0:
        logger.info(f"根据剩余可用时长 ({life}小时) 和流量 ({traffic}GB) 过滤订阅链接。")
        # Identify new subscriptions obtained in this run
        new_subscriptions = [x for x in urls if x not in old_subscriptions]
        # Prepare tasks to check status of new subscriptions (using basic check_status if available)
        # Note: check_status might still perform basic URL reachability checks, but not full proxy availability.
        tasks_check = [[x, 2, traffic, life, 0, True] for x in new_subscriptions]
        # Check status of new subscriptions
        results = utils.multi_thread_run(func=crawl.check_status, tasks=tasks_check, num_threads=args.num, show_progress=display)
        total = len(urls) # Total subscriptions before filtering
        # Keep new subscriptions that passed the status check
        filtered_new_subscriptions = [new_subscriptions[i] for i in range(len(new_subscriptions)) if results[i][0] and not results[i][1]]
        # Combine filtered new subscriptions with old subscriptions
        urls = filtered_new_subscriptions
        urls.extend(old_subscriptions) # Add back old subscriptions (they were already validated earlier)
        discard = total - len(urls) # Calculate discarded count
        logger.info(f"订阅链接过滤完成，总数: {total}, 保留: {len(urls)}, 丢弃: {discard}")
    else:
        logger.info("未设置剩余可用时长或流量，跳过订阅链接过滤。")
        # If no filtering, just use the collected subscription URLs


    # --- Push Updated Files to Repository ---
    # Push the updated list of valid subscriptions
    try:
        push_repo_file("subscribes.txt", "\n".join(urls))
        logger.info("subscribes.txt 已更新并推送到仓库。")
    except Exception as e:
        logger.error(f"推送 subscribes.txt 失败: {e}")

    # Push the updated list of valid domains (extracted from valid subscriptions)
    try:
        domains_lines = [utils.extract_domain(url=x, include_protocal=True) for x in urls]
        push_repo_file("valid-domains.txt", "\n".join(list(set(domains_lines)))) # Use set to ensure unique domains
        logger.info("valid-domains.txt 已更新并推送到仓库。")
    except Exception as e:
        logger.error(f"推送 valid-domains.txt 失败: {e}")

    # Push the updated list of domains with coupon/invite codes
    try:
        domains_txt_content = ""
        for k, v in domains_dict.items():
            line = k
            if v.get("coupon") or v.get("invite_code"):
                line += f"{manager.delimiter}{v.get('coupon','')}{manager.delimiter}{v.get('invite_code','')}"
            domains_txt_content += line + "\n"
        push_repo_file("domains.txt", domains_txt_content.strip())
        logger.info("domains.txt 已更新并推送到仓库。")
    except Exception as e:
        logger.error(f"推送 domains.txt 失败: {e}")

    # Push the coupons.txt file (assuming it might have been updated during crawling)
    try:
        push_repo_file("coupons.txt", repo_files.get("coupons.txt", ""))
        logger.info("coupons.txt 已推送到仓库。")
    except Exception as e:
        logger.error(f"推送 coupons.txt 失败: {e}")


    # Clean up clash working directory (even though we didn't use clash, the directory might exist)
    # Assuming workflow.cleanup can handle a non-existent directory or empty file list safely.
    clash_workspace = os.path.join(PATH, "clash")
    workflow.cleanup(clash_workspace, [])
    logger.info("聚合订阅过程完成。")


# Custom help formatter for argparse
class CustomHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        if action.choices:
            parts = []
            if action.option_strings:
                parts.extend(action.option_strings)
                # Special handling for nargs if it's not a flag and not the targets argument
                if action.nargs != 0 and action.option_strings != ["-t", "--targets"]:
                    default = action.dest.upper()
                    args_string = self._format_args(action, default)
                    parts[-1] += " " + args_string
                else:
                    # For targets, just show the options
                    pass # Keep the default formatting for choices
            else:
                # Positional arguments
                args_string = self._format_args(action, action.dest)
                parts.append(args_string)
            return ", ".join(parts)
        else:
            # Default formatting for other actions
            return super()._format_action_invocation(action)

# Main execution block
if __name__ == "__main__":
    # Setup argument parser with custom formatter
    parser = argparse.ArgumentParser(formatter_class=CustomHelpFormatter)
    # Removed -s/--skip argument as node checking is removed
    # Removed -u/--url argument as test URL is not needed without checking
    # Removed -d/--delay argument as delay is not needed for checking
    parser.add_argument("-a", "--all", dest="all", action="store_true", default=False, help="生成 clash 完整配置 (包含所有节点，不只可用节点)")
    parser.add_argument("-c", "--chuck", dest="chuck", action="store_true", default=False, help="丢弃可能需要人工验证的候选网站")
    # parser.add_argument("-d", "--delay", type=int, required=False, default=5000, help="允许的代理最大延迟 (毫秒)") # Removed
    parser.add_argument("-e", "--easygoing", dest="easygoing", action="store_true", default=False, help="遇到邮箱白名单问题时尝试使用 Gmail 别名")
    parser.add_argument("-f", "--flow", type=int, required=False, default=0, help="可用剩余流量，单位: GB (用于过滤订阅链接)")
    parser.add_argument("-g", "--gist", type=str, required=False, default=os.environ.get("GIST_LINK", ""), help="GitHub 用户名和 gist id，用 '/' 分隔 (目前代码未使用此参数)")
    parser.add_argument("-i", "--invisible", dest="invisible", action="store_true", default=False, help="不显示检测进度条")
    parser.add_argument("-k", "--key", type=str, required=False, default=os.environ.get("GIST_PAT", ""), help="用于编辑 gist 的 GitHub personal access token (已从环境变量读取)")
    parser.add_argument("-l", "--life", type=int, required=False, default=0, help="剩余可用时长，单位: 小时 (用于过滤订阅链接)")
    parser.add_argument("-n", "--num", type=int, required=False, default=64, help="处理任务使用的线程数") # Updated help text
    parser.add_argument("-o", "--overwrite", dest="overwrite", action="store_true", default=False, help="覆盖已存在的域名信息，强制重新爬取")
    parser.add_argument("-p", "--pages", type=int, required=False, default=sys.maxsize, help="爬取 Telegram 时的最大页数")
    parser.add_argument("-r", "--refresh", dest="refresh", action="store_true", default=False, help="仅使用现有订阅刷新并剔除过期节点，不注册新账号")
    # parser.add_argument("-s", "--skip", dest="skip", action="store_true", default=False, help="跳过可用性检测，直接使用过滤规则筛选节点") # Removed
    parser.add_argument("-t", "--targets", nargs="+", choices=subconverter.CONVERT_TARGETS, default=["clash", "v2ray", "singbox"], help=f"选择要生成的配置类型，默认为 clash, v2ray 和 singbox，支持: {', '.join(subconverter.CONVERT_TARGETS)}")
    # parser.add_argument("-u", "--url", type=str, required=False, default="https://www.google.com/generate_204", help="测试节点可用性使用的 URL") # Removed
    parser.add_argument("-v", "--vitiate", dest="vitiate", action="store_true", default=False, help="忽略 subconverter 默认代理过滤规则")
    parser.add_argument("-y", "--yourself", type=str, required=False, default=os.environ.get("CUSTOMIZE_LINK", ""), help="你维护的机场列表的 URL (格式与 domains.txt 类似)")

    # Parse command line arguments and run the aggregation process
    aggregate_no_check(args=parser.parse_args())
