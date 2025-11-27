import os
import re
from base64 import b64decode, b64encode
from collections import defaultdict
from copy import deepcopy
from random import randint
from time import time
from urllib.parse import quote, urljoin

from ruamel.yaml import YAML

from apis import Response, Session
# from get_trial_update_url import get_short_url
from utils import (DOMAIN_SUFFIX_Tree, IP_CIDR_SegmentTree, cached,
                   clear_files, get_name, list_file_paths, re_non_empty_base64,
                   read, read_cfg, write)

github_raw_url_prefix = f"https://raw.kgithub.com/{os.getenv('GITHUB_REPOSITORY')}/{os.getenv('GITHUB_REF_NAME')}"

subconverters = [row[0] for row in read_cfg('subconverters.cfg')['default']]


def _yaml():
    yaml = YAML()
    yaml.version = (1, 1)
    yaml.width = float('inf')
    return yaml


def _get_by_any(session: Session, url, retry_400=99) -> Response:
    r = None

    def get():
        nonlocal retry_400, r
        try:
            r = session.get(url)
            if r.ok:
                return True
            if 400 <= r.status_code < 500:
                if retry_400 <= 0:
                    return True
                retry_400 -= 1
        except Exception:
            pass
        return False

    if session.host:
        if get():
            return r
        url_parsed = parse_url(url)
        if url_parsed.host and url_parsed.host not in session.host:
            r = get_by_first_match(session, url)
            if r:
                return r

    r = get_by_first_match(session, url)
    if r:
        return r
    
    if r:
        return r

    r = session.get(url)
    return r


@cached(lambda: f'{os.getenv("GITHUB_REPOSITORY")}-{os.getenv("GITHUB_REF_NAME")}')
def _get_by_all(url, get_by_first_match, session: Session = None) -> list[Response]:
    urls = [f'{row[0]}?target=base64&url={quote(url)}&config={row[1]}' for row in read_cfg('subconverters.cfg')['default']]
    if not session:
        session = Session('', 0)

    rs = parallel_map(lambda url: _get_by_any(session, url, retry_400=0), urls)
    return [r for r in rs if r and r.ok]


def get_by_first_match(session: Session, url):
    for subconverter, config in read_cfg('subconverters.cfg')['default']:
        r = _get_by_any(session, f'{subconverter}?target=base64&url={quote(url)}&config={config}', retry_400=0)
        if r and r.ok:
            return r


def get(url, get_by_all=False) -> list[Response]:
    if get_by_all:
        return _get_by_all(url, get_by_first_match)
    r = get_by_first_match(Session('', 0), url)
    return [r] if r else []


def _rules():
    return [
        'DOMAIN-SUFFIX,googlevideo.com,YouTube',
        'DOMAIN-SUFFIX,youtube.com,YouTube',
        'DOMAIN-SUFFIX,youtu.be,YouTube',
        'DOMAIN-SUFFIX,twitter.com,Twitter',
        'DOMAIN-SUFFIX,t.co,Twitter',
        'DOMAIN-SUFFIX,twimg.com,Twitter',
        'DOMAIN-SUFFIX,google.com,Google',
        'DOMAIN-SUFFIX,facebook.com,Facebook',
        'DOMAIN-SUFFIX,fb.me,Facebook',
        'DOMAIN-SUFFIX,fbcdn.net,Facebook',
        'DOMAIN-SUFFIX,instagram.com,Instagram',
        'DOMAIN-SUFFIX,steamcommunity.com,Steam',
        'DOMAIN-SUFFIX,steampowered.com,Steam',
        'DOMAIN-SUFFIX,steamgames.com,Steam',
        'DOMAIN-SUFFIX,github.com,Github',
        'DOMAIN-SUFFIX,githubassets.com,Github',
        'DOMAIN-SUFFIX,githubusercontent.com,Github',
        'DOMAIN-SUFFIX,v2ray.com,V2ray',
        'DOMAIN-SUFFIX,telegram.org,Telegram',
        'DOMAIN-SUFFIX,t.me,Telegram',
        'DOMAIN-SUFFIX,medium.com,Medium',
        'DOMAIN-SUFFIX,wikipedia.org,Wikipedia',
        'DOMAIN-SUFFIX,wikimedia.org,Wikipedia',
        'DOMAIN-SUFFIX,pornhub.com,Pornhub',
        'DOMAIN-SUFFIX,xhamster.com,Xhamster',
        'DOMAIN-SUFFIX,xvideos.com,Xvideos',
        'DOMAIN-SUFFIX,xnxx.com,Xnxx',
        'GEOIP,CN,DIRECT',
        'MATCH,Proxy'
    ]


def _base_yaml():
    return {
        'port': 7890,
        'socks-port': 7891,
        'allow-lan': True,
        'mode': 'rule',
        'log-level': 'info',
        'external-controller': '127.0.0.1:9090',
        'proxies': [],
        'proxy-groups': [
            {'name': 'Proxy', 'type': 'select', 'proxies': ['🎯 自动选择', '♻️ 负载均衡', '🇭🇰 香港节点', '🇯🇵 日本节点', '🇹🇼 台湾节点', '🇸🇬 新加坡节点', '🇺🇸 美国节点', 'DIRECT']},
            {'name': '🎯 自动选择', 'type': 'url-test', 'url': 'http://www.gstatic.com/generate_204', 'interval': 300, 'proxies': []},
            {'name': '♻️ 负载均衡', 'type': 'load-balance', 'url': 'http://www.gstatic.com/generate_204', 'interval': 300, 'proxies': []},
            {'name': '🇭🇰 香港节点', 'type': 'select', 'proxies': []},
            {'name': '🇯🇵 日本节点', 'type': 'select', 'proxies': []},
            {'name': '🇹🇼 台湾节点', 'type': 'select', 'proxies': []},
            {'name': '🇸🇬 新加坡节点', 'type': 'select', 'proxies': []},
            {'name': '🇺🇸 美国节点', 'type': 'select', 'proxies': []},
            {'name': 'DIRECT', 'type': 'select', 'proxies': ['DIRECT']},
            {'name': 'Domestic', 'type': 'select', 'proxies': ['DIRECT', 'Proxy']},
            {'name': 'YouTube', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Twitter', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Google', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Facebook', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Instagram', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Steam', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Github', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'V2ray', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Telegram', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Medium', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Wikipedia', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Pornhub', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Xhamster', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Xvideos', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
            {'name': 'Xnxx', 'type': 'select', 'proxies': ['Proxy', 'DIRECT']},
        ],
        'proxy-providers': {}
    }


def _group_to_proxy_providers(cfg: dict, provider_map: dict):
    for group in cfg['proxy-groups']:
        if group['name'] not in ('Proxy', '🎯 自动选择', '♻️ 负载均衡'):
            group['proxies'] = list(set(provider_map.get(group['name'], [])) & set(group['proxies']))


def _remove_redundant_groups(cfg: dict, provider_map: dict):
    names = set(provider_map)
    cfg['proxy-groups'] = [group for group in cfg['proxy-groups'] if group['name'] in names or group['name'] in ('Proxy', '🎯 自动选择', '♻️ 负载均衡', 'DIRECT', 'Domestic', *[group['name'] for group in cfg['proxy-groups'] if group['name'] not in names and group['proxies']])]
    cfg['proxy-groups'] = [group for group in cfg['proxy-groups'] if group['name'] not in ('🎯 自动选择', '♻️ 负载均衡') or len(group['proxies']) > 0]
    
    for group in cfg['proxy-groups']:
        group['proxies'] = [proxy for proxy in group['proxies'] if proxy != group['name']]

    for group in cfg['proxy-groups']:
        if group['name'] not in ('Proxy', 'DIRECT'):
            group['proxies'].insert(0, 'DIRECT')
            group['proxies'].append('Proxy')


def _group_by_country(node_map: dict) -> dict:
    country_map = defaultdict(list)
    for name, node in node_map.items():
        country_map[node['name'].split()[0].replace('🇹🇼', '台湾').replace('🇭🇰', '香港').replace('🇯🇵', '日本').replace('🇸🇬', '新加坡').replace('🇺🇸', '美国')].append(name)
    return country_map


def _to_providers(country_map: dict) -> tuple[dict, dict]:
    provider_map = defaultdict(list)
    real_providers = {}
    to_real_providers = {}

    for country, names in country_map.items():
        provider_name = f'{country}-all'
        
        if len(names) > 30:
            to_real_providers[country] = provider_name
            real_providers[provider_name] = names
        else:
            provider_map[country].extend(names)
            
    return provider_map, real_providers


def _to_proxies(cfg: dict, provider_map: dict):
    for group in cfg['proxy-groups']:
        if group['name'] in provider_map:
            group['proxies'].extend(provider_map[group['name']])


def _to_real_providers(cfg: dict, to_real_providers: dict):
    for group in cfg['proxy-groups']:
        if group['name'] in to_real_providers:
            group['proxies'].append(to_real_providers[group['name']])


def _add_proxy_providers(cfg: dict, real_providers: dict, providers_dir: str, use_base_url: bool):
    y = _yaml()
    for provider_name, names in real_providers.items():
        provider_path = os.path.join(providers_dir, f'{provider_name}.yaml')
        write(provider_path, lambda f: y.dump({'proxies': [node_map[name] for name in names]}, f))

        url = f'{github_raw_url_prefix}/{provider_path}' if use_base_url else f'{get_short_url(provider_path)}'

        cfg['proxy-providers'][provider_name] = {
            'type': 'http',
            'url': url,
            'interval': 3600,
            'health-check': {'enable': True, 'url': 'http://www.gstatic.com/generate_204', 'interval': 300},
            'path': provider_path,
            'lazy': True
        }


def gen_base64_and_clash_config(base64_path, clash_path, providers_dir, base64=None, base64_paths=None, provider_paths=None) -> int:
    y = _yaml()
    base64_node_n = _gen_base64_config(base64_path, node_map, base64, base64_paths)
    
    if os.path.exists(providers_dir):
        clear_files(providers_dir)

    name_to_node_map, node_map = _gen_name_to_node_map(base64_node_n, base64_path)

    if base64_node_n != len(name_to_node_map):
        print(f'base64 ({base64_node_n}) 与 clash {len(name_to_node_map)} 节点数量不一致')
    return base64_node_n


def _gen_clash_config(y, clash_path, providers_dir, name_to_node_map, provider_map, to_real_providers, real_providers):
    cfg = deepcopy(_base_yaml())
    del cfg['proxy-providers']
    _remove_redundant_groups(cfg, provider_map)
    hardcode_cfg = deepcopy(cfg)

    _to_real_providers(cfg, to_real_providers)
    _add_proxy_providers(cfg, real_providers, providers_dir, clash_path == 'trial.yaml')
    cfg['rules'] = _rules()

    _to_proxies(hardcode_cfg, provider_map)
    hardcode_cfg['proxies'] = [*name_to_node_map.values()]
    hardcode_cfg['rules'] = _rules()

    write(clash_path, lambda f: y.dump(hardcode_cfg, f))
    prefix, ext = os.path.splitext(clash_path)
    write(f'{prefix}_pp{ext}', lambda f: y.dump(cfg, f))


def _gen_base64_config(base64_path, name_to_node_map, base64=None, base64_paths=None):
    if base64_paths:
        base64s = (read(path, True) for path in base64_paths)
    else:
        base64s = [base64]
    
    for base64 in base64s:
        if base64 and re_non_empty_base64.search(base64):
            try:
                base64 = b64decode(base64).decode()
            except Exception:
                pass
            
            node_map = {}
            for line in base64.splitlines():
                if line:
                    node = get_name(line)
                    if node:
                        node_map[node['name']] = node
            
            name_to_node_map.update(node_map)
            
            if len(base64.splitlines()) != len(node_map):
                print(f'base64 节点数量 {len(base64.splitlines())} 与解析后数量 {len(node_map)} 不一致')
                
    write(base64_path, lambda f: f.write(b64encode('\n'.join(name_to_node_map).encode()).decode()))
    return len(name_to_node_map)


def _gen_name_to_node_map(base64_node_n, base64_path):
    base64 = b64decode(read(base64_path, True)).decode()
    name_to_node_map = {}
    
    for line in base64.splitlines():
        if line:
            node = get_name(line)
            if node:
                name_to_node_map[node['name']] = node
    
    return name_to_node_map, {name: node for name, node in name_to_node_map.items() if node['name'].split()[0] in ('🇭🇰', '🇯🇵', '🇹🇼', '🇸🇬', '🇺🇸')}
