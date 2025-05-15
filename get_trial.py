import asyncio
import aiohttp
from typing import Optional, Tuple
import logging
import os
from datetime import timedelta
from random import choice, randint
from time import time
from urllib.parse import urlsplit, urlunsplit
import backoff

from apis import PanelSession, TempEmail, guess_panel, panel_class_map
from subconverter import gen_base64_and_clash_config, get
from utils import (clear_files, g0, keep, list_file_paths, list_folder_paths,
                  rand_id, read, read_cfg, remove, size2str, str2timestamp,
                  timestamp2str, to_zero, write, write_cfg)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_WORKERS = 8  # 减少并发线程数
MAX_TASK_TIMEOUT = 45  # 单任务超时时间（秒）

# 带重试的装饰器
@backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_tries=5)
async def _send_email_code(session: aiohttp.ClientSession, host: str, email: str):
    """异步发送邮箱验证码"""
    async with session.post(f"{host}/send_email_code", json={'email': email}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status != 200:
            raise Exception(f'发送验证码失败: {await resp.text()}')

async def _get_email_and_email_code_async(session: aiohttp.ClientSession, kwargs: dict, opt: dict, cache: dict) -> str:
    """异步获取邮箱和验证码，带重试和超时控制"""
    retry = 0
    while retry < 5:
        tm = TempEmail(banned_domains=cache.get('banned_domains', []))
        try:
            email = kwargs['email'] = tm.email
        except Exception as e:
            raise Exception(f'获取邮箱失败: {e}')
        
        try:
            await _send_email_code(session, kwargs['host'], email)
        except Exception as e:
            msg = str(e)
            if '禁' in msg or '黑' in msg:
                cache.setdefault('banned_domains', []).append(email.split('@')[1])
                retry += 1
                continue
            raise Exception(f'发送邮箱验证码失败({email}): {e}')
        
        email_code = await asyncio.to_thread(tm.get_email_code, g0(cache, 'name'))  # 异步获取验证码
        if not email_code:
            cache.setdefault('banned_domains', []).append(email.split('@')[1])
            retry += 1
            continue
        kwargs['email_code'] = email_code
        return email
    raise Exception('获取邮箱验证码失败，重试次数过多')

@backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_tries=3)
async def get_sub_async(session: aiohttp.ClientSession, host: str, opt: dict, cache: dict) -> Optional[Tuple]:
    """异步获取订阅信息"""
    url = cache['sub_url'][0]
    suffix = ' - ' + g0(cache, 'name')
    if 'speed_limit' in opt:
        suffix += ' ⚠️限速 ' + opt['speed_limit']
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                info, base64_content, clash_content = get(text, suffix)  # 调用原有的 get 函数
                return info, base64_content, clash_content
            else:
                logger.warning(f"获取订阅失败({host}): {resp.status}")
                return None
    except Exception as e:
        logger.error(f"获取订阅异常({host}): {e}")
        return None

async def try_turn_async(session: aiohttp.ClientSession, host: str, opt: dict, cache: dict, log: list) -> Optional[Tuple]:
    """异步尝试更新订阅"""
    try:
        sub = await get_sub_async(session, host, opt, cache)
        if not sub:  # 如果订阅无效或需要更新
            panel_session = new_panel_session(host, cache, log)
            if panel_session:
                do_turn(panel_session, opt, cache, log)
                cache['sub_url'] = [panel_session.get_sub_url(**opt)]
                log.append(f"更新订阅链接({host}) {cache['sub_url'][0]}")
                sub = await get_sub_async(session, host, opt, cache)
        return sub
    except Exception as e:
        log.append(f"更新订阅链接/续费续签失败({host}): {e}")
        return None

async def save_sub_async(info, base64, clash, host: str, opt: dict, cache: dict, log: list):
    """异步保存订阅"""
    if not info or not base64 or not clash:
        log.append(f"保存base64/clash订阅失败({host}): 数据无效")
        return
    try:
        cache_sub_info(info, opt, cache)
        node_n = save_sub_base64_and_clash(base64, clash, host, opt)
        if (d := node_n - int(g0(cache, 'node_n', 0))) != 0:
            log.append(f'{host} 节点数 {"+" if d > 0 else ""}{d} ({node_n})')
        cache['node_n'] = node_n
        logger.info(f"保存订阅成功({host})")
    except Exception as e:
        log.append(f"保存base64/clash订阅失败({host}): {e}")

async def get_and_save_async(http_session: aiohttp.ClientSession, host: str, opt: dict, cache: dict, log: list):
    """异步获取并保存订阅"""
    try:
        sub = await try_turn_async(http_session, host, opt, cache, log)
        if sub:
            await save_sub_async(*sub, host, opt, cache, log)
    except Exception as e:
        log.append(f"{host} get_and_save 异常: {e}")

async def get_trial_async(host: str, opt: dict, cache: dict) -> list:
    """异步执行单个任务"""
    log = []
    async with aiohttp.ClientSession() as session:
        try:
            kwargs = {'host': host}  # 为 _get_email_and_email_code_async 提供 host 参数
            await get_and_save_async(session, host, opt, cache, log)
        except Exception as e:
            log.append(f"{host} 处理异常: {e}")
    return log

# 以下为未修改的辅助函数，直接从原代码中保留
def should_turn(session: PanelSession, opt: dict, cache: dict[str, list[str]]):
    if 'sub_url' not in cache:
        return 1,

    now = time()
    try:
        info, *rest = get_sub(session, opt, cache)
    except Exception as e:
        msg = str(e)
        if '邮箱' in msg and ('不存在' in msg or '禁' in msg or '黑' in msg):
            if (d := cache['email'][0].split('@')[1]) not in ('gmail.com', 'qq.com', g0(cache, 'email_domain')):
                cache['banned_domains'].append(d)
            return 2,
        raise e

    return int(
        not info
        or opt.get('turn') == 'always'
        or float(info['total']) - (float(info['upload']) + float(info['download'])) < (1 << 28)
        or (opt.get('expire') != 'never' and info.get('expire') and str2timestamp(info.get('expire')) - now < ((now - str2timestamp(cache['time'][0])) / 7 if 'reg_limit' in opt else 2400))
    ), info, *rest

def _register(session: PanelSession, email, *args, **kwargs):
    try:
        return session.register(email, *args, **kwargs)
    except Exception as e:
        raise Exception(f'注册失败({email}): {e}')

def register(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list) -> bool:
    kwargs = keep(opt, 'name_eq_email', 'reg_fmt', 'aff')

    if 'invite_code' in cache:
        kwargs['invite_code'] = cache['invite_code'][0]
    elif 'invite_code' in opt:
        kwargs['invite_code'] = choice(opt['invite_code'].split())

    email = kwargs['email'] = f"{rand_id()}@{g0(cache, 'email_domain', default='gmail.com')}"
    retry = 0
    while retry < 5:
        if not (msg := _register(session, **kwargs)):
            if g0(cache, 'auto_invite', 'T') == 'T' and hasattr(session, 'get_invite_info'):
                if 'buy' not in opt and 'invite_code' not in kwargs:
                    session.login()
                    try:
                        code, num, money = session.get_invite_info()
                    except Exception as e:
                        if g0(cache, 'auto_invite') == 'T':
                            log.append(f'{session.host}({email}): {e}')
                        if '邀请' in str(e):
                            cache['auto_invite'] = 'F'
                        return False
                    if 'auto_invite' not in cache:
                        if not money:
                            cache['auto_invite'] = 'F'
                            return False
                        balance = session.get_balance()
                        plan = session.get_plan(min_price=balance + 0.01, max_price=balance + money)
                        if not plan:
                            cache['auto_invite'] = 'F'
                            return False
                        cache['auto_invite'] = 'T'
                    cache['invite_code'] = [code, num]
                    kwargs['invite_code'] = code

                    session.reset()

                    if 'email_code' in kwargs:
                        email = kwargs['email']  # 假设已有异步获取逻辑
                    else:
                        email = kwargs['email'] = f"{rand_id()}@{email.split('@')[1]}"

                    if (msg := _register(session, **kwargs)):
                        break

                if 'invite_code' in kwargs:
                    if 'invite_code' not in cache or int(cache['invite_code'][1]) == 1 or randint(0, 1):
                        session.login()
                        try_buy(session, opt, cache, log)
                        try:
                            cache['invite_code'] = [*session.get_invite_info()[:2]]
                        except Exception as e:
                            if 'invite_code' not in cache:
                                cache['auto_invite'] = 'F'
                            else:
                                log.append(f'{session.host}({email}): {e}')
                        return True
                    else:
                        n = int(cache['invite_code'][1])
                        if n > 0:
                            cache['invite_code'][1] = n - 1
            return False
        if '后缀' in msg:
            if email.split('@')[1] != 'gmail.com':
                break
            email = kwargs['email'] = f'{rand_id()}@qq.com'
        elif '验证码' in msg:
            email = kwargs['email']  # 假设已有异步获取逻辑
        elif '联' in msg:
            kwargs['im_type'] = True
        elif (
            '邀请人' in msg
            and g0(cache, 'invite_code', '') == kwargs.get('invite_code')
        ):
            del cache['invite_code']
            if 'invite_code' in opt:
                kwargs['invite_code'] = choice(opt['invite_code'].split())
            else:
                del kwargs['invite_code']
        else:
            break
        retry += 1
    if retry >= 5:
        raise Exception(f'注册失败({email}): {msg}{" " + kwargs.get("invite_code") if "邀" in msg else ""}')
    return True

def is_checkin(session, opt: dict):
    return hasattr(session, 'checkin') and opt.get('checkin') != 'F'

def try_checkin(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list):
    if is_checkin(session, opt) and cache.get('email'):
        if len(cache['last_checkin']) < len(cache['email']):
            cache['last_checkin'] += ['0'] * (len(cache['email']) - len(cache['last_checkin']))
        last_checkin = to_zero(str2timestamp(cache['last_checkin'][0]))
        now = time()
        if now - last_checkin > 24.5 * 3600:
            try:
                session.login(cache['email'][0])
                session.checkin()
                cache['last_checkin'][0] = timestamp2str(now)
                cache.pop('尝试签到失败', None)
            except Exception as e:
                cache['尝试签到失败'] = [e]
                log.append(f'尝试签到失败({session.host}): {e}')
    else:
        cache.pop('last_checkin', None)

def try_buy(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list):
    try:
        if (plan := opt.get('buy')):
            return session.buy(plan)
        if (plan := g0(cache, 'buy')):
            if plan == 'pass':
                return False
            try:
                return session.buy(plan)
            except Exception as e:
                del cache['buy']
                cache.pop('auto_invite', None)
                cache.pop('invite_code', None)
                log.append(f'上次购买成功但这次购买失败({session.host}): {e}')
        plan = session.buy()
        cache['buy'] = plan or 'pass'
        return plan
    except Exception as e:
        log.append(f'购买失败({session.host}): {e}')
    return False

def do_turn(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list, force_reg=False) -> bool:
    is_new_reg = False
    login_and_buy_ok = False
    reg_limit = opt.get('reg_limit')
    if not reg_limit:
        login_and_buy_ok = register(session, opt, cache, log)
        is_new_reg = True
        cache['email'] = [session.email]
        if is_checkin(session, opt):
            cache['last_checkin'] = ['0']
    else:
        reg_limit = int(reg_limit)
        if len(cache['email']) < reg_limit or force_reg:
            login_and_buy_ok = register(session, opt, cache, log)
            is_new_reg = True
            cache['email'].append(session.email)
            if is_checkin(session, opt):
                cache['last_checkin'] += ['0'] * (len(cache['email']) - len(cache['last_checkin']))
        if len(cache['email']) > reg_limit:
            del cache['email'][:-reg_limit]
            if is_checkin(session, opt):
                del cache['last_checkin'][:-reg_limit]

        cache['email'] = cache['email'][-1:] + cache['email'][:-1]
        if is_checkin(session, opt):
            cache['last_checkin'] = cache['last_checkin'][-1:] + cache['last_checkin'][:-1]

    if not login_and_buy_ok:
        try:
            session.login(cache['email'][0])
        except Exception as e:
            raise Exception(f'登录失败: {e}')
        try_buy(session, opt, cache, log)

    try_checkin(session, opt, cache, log)
    cache['sub_url'] = [session.get_sub_url(**opt)]
    cache['time'] = [timestamp2str(time())]
    log.append(f'{"更新订阅链接(新注册)" if is_new_reg else "续费续签"}({session.host}) {cache["sub_url"][0]}')

def cache_sub_info(info, opt: dict, cache: dict[str, list[str]]):
    if not info:
        raise Exception('no sub info')
    used = float(info["upload"]) + float(info["download"])
    total = float(info["total"])
    rest = '(剩余 ' + size2str(total - used)
    if opt.get('expire') == 'never' or not info.get('expire'):
        expire = '永不过期'
    else:
        ts = str2timestamp(info['expire'])
        expire = timestamp2str(ts)
        rest += ' ' + str(timedelta(seconds=ts - time()))
    rest += ')'
    cache['sub_info'] = [size2str(used), size2str(total), expire, rest]

def save_sub_base64_and_clash(base64, clash, host, opt: dict):
    return gen_base64_and_clash_config(
        base64_path=f'trials/{host}',
        clash_path=f'trials/{host}.yaml',
        providers_dir=f'trials_providers/{host}',
        base64=base64,
        clash=clash,
        exclude=opt.get('exclude')
    )

def new_panel_session(host, cache: dict[str, list[str]], log: list) -> PanelSession | None:
    try:
        if 'type' not in cache:
            info = guess_panel(host)
            if 'type' not in info:
                if (e := info.get('error')):
                    log.append(f"{host} 判别类型失败: {e}")
                else:
                    log.append(f"{host} 未知类型")
                return None
            cache.update(info)
        return panel_class_map[g0(cache, 'type')](g0(cache, 'api_host', host), **keep(cache, 'auth_path', getitem=g0))
    except Exception as e:
        log.append(f"{host} new_panel_session 异常: {e}")
        return None

def build_options(cfg):
    opt = {
        host: dict(zip(opt[::2], opt[1::2]))
        for host, *opt in cfg
    }
    return opt

async def main():
    pre_repo = read('.github/repo_get_trial')
    cur_repo = os.getenv('GITHUB_REPOSITORY')
    if pre_repo != cur_repo:
        remove('trial.cache')
        write('.github/repo_get_trial', cur_repo)

    cfg = read_cfg('trial.cfg')['default']
    opt = build_options(cfg)
    cache = read_cfg('trial.cache', dict_items=True)

    for host in [*cache]:
        if host not in opt:
            del cache[host]

    for path in list_file_paths('trials'):
        host, ext = os.path.splitext(os.path.basename(path))
        if ext != '.yaml':
            host += ext
        else:
            host = host.split('_')[0]
        if host not in opt:
            remove(path)

    for path in list_folder_paths('trials_providers'):
        host = os.path.basename(path)
        if '.' in host and host not in opt:
            clear_files(path)
            remove(path)

    tasks = [get_trial_async(h, opt[h], cache[h]) for h, *_ in cfg]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"任务异常: {result}")
        else:
            for line in result:
                print(line, flush=True)

    total_node_n = gen_base64_and_clash_config(
        base64_path='trial',
        clash_path='trial.yaml',
        providers_dir='trials_providers',
        base64_paths=(path for path in list_file_paths('trials') if os.path.splitext(path)[1].lower() != '.yaml'),
        providers_dirs=(path for path in list_folder_paths('trials_providers') if '.' in os.path.basename(path))
    )

    print('总节点数', total_node_n)
    write_cfg('trial.cache', cache)

if __name__ == '__main__':
    asyncio.run(main())
