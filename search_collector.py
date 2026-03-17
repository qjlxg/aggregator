import asyncio
import random
import urllib.parse
from playwright.async_api import async_playwright 

# 核心指纹列表 - 使用你验证过的最准的路径
KEYWORDS = [
    'intext:"/theme/v2board/assets/umi.js"',
    'intext:"window.settings" assets_path theme v2board',
    'intext:"/theme/v2board/assets/vendors.async.js"'
]

async def run_search():
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        all_links = set()

        for query in KEYWORDS:
            encoded_query = urllib.parse.quote(query)
            # 使用 DDG HTML 简洁版，对数据中心 IP 极其友好
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            
            print(f"[*] 正在抓取指纹: {query}")
            try:
                # DDG HTML 版加载极快
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                # 抓取前 3 页（DDG HTML 版通过 form 提交翻页）
                for page_num in range(3):
                    # 提取链接
                    links = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('.result__url'))
                            .map(a => a.href.trim())
                            .filter(href => href && !href.includes('duckduckgo.com'));
                    }''')
                    
                    all_links.update(links)
                    print(f"    - 第 {page_num + 1} 页发现 {len(links)} 个潜在目标")

                    # 尝试翻页
                    next_btn = page.locator('input[value="Next"]').first
                    if await next_btn.is_visible():
                        await next_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))
                    else:
                        break
            except Exception as e:
                print(f"[!] 抓取中断: {e}")

        await browser.close()

        # 最终保存
        with open("search_results.txt", "w", encoding="utf-8") as f:
            if all_links:
                f.write("\n".join(sorted(list(all_links))))
                print(f"\n[+] 完工！共捕获 {len(all_links)} 个站点链接。")
            else:
                f.write("")
                print("\n[!] 未能捕获任何链接，建议手动检查指纹在 DDG 上的表现。")

if __name__ == "__main__":
    asyncio.run(run_search())
