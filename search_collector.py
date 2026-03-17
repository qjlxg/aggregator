import asyncio
import random
import sys
import urllib.parse
# 关键修正：使用 async_api 路径
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
        # 伪造更真实的浏览器指纹
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        all_links = set()

        for query in KEYWORDS:
            encoded_query = urllib.parse.quote(query)
            # 这里的日期是根据你之前要求的 2026-03-13 到 2026-03-17
            search_url = f"https://www.google.com/search?q={encoded_query}&tbs=cdr:1,cd_min:3/13/2026,cd_max:3/17/2026"
            
            print(f"[*] 正在搜索: {query}")
            try:
                # 模拟更像人的行为：增加随机延迟
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(random.uniform(5, 10))

                for page_num in range(3): # 每次搜索跑 3 页，降低被封风险
                    # 提取链接逻辑
                    links = await page.evaluate('''() => {
                        const anchors = Array.from(document.querySelectorAll('div.g a'));
                        return anchors
                            .map(a => a.href)
                            .filter(href => href && href.startsWith('http') && !href.includes('google.com') && !href.includes('gstatic.com'));
                    }''')
                    
                    all_links.update(links)
                    print(f"    - 第 {page_num + 1} 页抓取到 {len(links)} 条原始链接")

                    # 翻页逻辑：寻找“下一页”
                    next_button = page.locator('a#pnnext, a:has-text("下一页"), a:has-text("Next")').first
                    if await next_button.is_visible():
                        await next_button.click()
                        await asyncio.sleep(random.uniform(5, 8))
                    else:
                        break
            except Exception as e:
                print(f"[!] 搜索过程出错: {e}")

        await browser.close()

        # 写入结果
        if all_links:
            with open("search_results.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(list(all_links))))
            print(f"\n[+] 任务成功：保存了 {len(all_links)} 条链接到 search_results.txt")
        else:
            print("\n[!] 警告：未抓取到任何结果，可能是触发了 Google 验证码（CAPTCHA）。")

if __name__ == "__main__":
    asyncio.run(run_search())
