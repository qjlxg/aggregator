import asyncio
import random
import urllib.parse
from playwright.async_api import async_playwright 

# 搜索关键词列表
KEYWORDS = [
    'intext:"v2board" OR intext:"xboard"',
    'intext:"SSPanel-Uim" OR intext:"/theme/Rocket/assets/"',
    'intext:"layouts__index.async.js"'
]

async def run_search():
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        all_links = set()

        for query in KEYWORDS:
            encoded_query = urllib.parse.quote(query)
            # Bing 的日期过滤通常在搜索框内使用，或者通过 URL 参数，但最稳妥的是直接搜索
            search_url = f"https://www.bing.com/search?q={encoded_query}"
            
            print(f"[*] 正在 Bing 搜索: {query}")
            try:
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(random.uniform(3, 6))

                for page_num in range(3): 
                    # Bing 的结果通常在 li.b_algo 中
                    links = await page.evaluate('''() => {
                        const anchors = Array.from(document.querySelectorAll('li.b_algo h2 a, .b_algo header a'));
                        return anchors
                            .map(a => a.href)
                            .filter(href => href && href.startsWith('http') && !href.includes('bing.com') && !href.includes('microsoft.com'));
                    }''')
                    
                    all_links.update(links)
                    print(f"    - 第 {page_num + 1} 页抓取到 {len(links)} 条链接")

                    # Bing 的下一页按钮通常带有 title="下一页" 或类名 sb_pagN
                    next_button = page.locator('a[title="下一页"], a.sb_pagN').first
                    if await next_button.is_visible():
                        await next_button.click()
                        await asyncio.sleep(random.uniform(4, 7))
                    else:
                        break
            except Exception as e:
                print(f"[!] 搜索过程出错: {e}")

        await browser.close()

        # 始终创建文件，避免 Git 报错
        with open("search_results.txt", "w", encoding="utf-8") as f:
            if all_links:
                f.write("\n".join(sorted(list(all_links))))
                print(f"\n[+] 任务成功：保存了 {len(all_links)} 条链接")
            else:
                f.write("") 
                print("\n[!] 警告：Bing 也没返回结果，可能需要检查关键词。")

if __name__ == "__main__":
    asyncio.run(run_search())
