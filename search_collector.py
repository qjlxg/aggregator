import asyncio
import random
from playwright.asyncio import sys, create_playwright

# 搜索关键词列表
KEYWORDS = [
    'intext:"v2board" OR intext:"xboard"',
    'intext:"SSPanel-Uim" OR intext:"/theme/Rocket/assets/"',
    'intext:"layouts__index.async.js"'
]

async def run_search():
    async with create_playwright() as p:
        # 使用随机 User-Agent
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        all_links = set()

        for query in KEYWORDS:
            # 构建带有日期过滤的 URL (Google 专用)
            # 搜索 2026-03-13 到 2026-03-17 的结果
            search_url = f"https://www.google.com/search?q={query}&tbs=cdr:1,cd_min:3/13/2026,cd_max:3/17/2026"
            
            await page.goto(search_url)
            await asyncio.sleep(random.uniform(2, 5)) # 随机等待防止被封

            for _ in range(5):  # 默认抓取前 5 页
                # 提取链接
                links = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('div.g a'))
                        .map(a => a.href)
                        .filter(href => href.startsWith('http') && !href.includes('google.com'));
                }''')
                all_links.update(links)

                # 尝试点击“下一页”
                next_button = page.locator('a#pnnext')
                if await next_button.count() > 0:
                    await next_button.click()
                    await asyncio.sleep(random.uniform(3, 6))
                else:
                    break

        await browser.close()

        # 保存结果
        with open("search_results.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(list(all_links))))
        print(f"抓取完成，共获得 {len(all_links)} 条独立链接。")

if __name__ == "__main__":
    asyncio.run(run_search())
