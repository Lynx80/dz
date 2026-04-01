import asyncio
import re
import time
from playwright.async_api import async_playwright
from database.db import Database

class ParserService:
    def __init__(self, db=None):
        self.db = db or Database()
        self.DEBUG = False # Set to True for step-by-step screenshots

    async def _solve_vnet(self, user, test_url, status_cb, ss_cb):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            try:
                if status_cb: await status_cb("[CMD] Starting Optimized Solver...")
                await page.goto(test_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(3)
                
                # Fast Login
                inputs = await page.query_selector_all("input.input")
                if len(inputs) >= 3:
                    await inputs[0].fill(user.get('last_name', 'Student'))
                    await inputs[1].fill(user.get('first_name', 'Robot'))
                    await inputs[2].fill("11")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(8)

                q_data = await page.evaluate("() => JSON.parse(window.backend?.questions || '{}')")
                qs = list(q_data.values()) if isinstance(q_data, dict) else (q_data or [])
                
                for i in range(len(qs)):
                    if status_cb: await status_cb(f"[VNET] Q{i+1}")
                    try: 
                        await page.get_by_text(f"Вопрос {i+1}", exact=False).first.click(force=True, timeout=2000)
                    except: pass
                    
                    q_info = qs[i]
                    opts = q_info.get('options', [])
                    
                    # 1. Input Field
                    ti = await page.query_selector("input[type='text'], textarea, .el-input__inner")
                    if ti and not opts:
                        ans = q_info.get('answer', q_info.get('correct_answer', ''))
                        if ans: await ti.fill(str(ans)); await asyncio.sleep(0.5)

                    # 2. Selects/Dropdowns
                    sels = await page.query_selector_all(".el-select, .el-input__inner")
                    if sels and opts:
                        for s_idx, sel in enumerate(sels):
                            if s_idx < len(opts):
                                t = opts[s_idx].get('name', '')
                                try:
                                    await sel.click(force=True); await asyncio.sleep(0.5)
                                    await page.locator(f"xpath=//span[contains(text(), '{t}')]").first.click(force=True, timeout=1000)
                                except: pass

                    # 3. Regular Clicks
                    corrs = [o.get('name', '') for o in opts if o.get('correct') or o.get('is_correct') == 1]
                    for ct in corrs:
                        try: await page.get_by_text(ct).first.click(force=True, timeout=1500)
                        except: pass

                    if self.DEBUG:
                        ss = f"tmp/proof_q{i+1}.png"
                        await page.screenshot(path=ss)
                        if status_cb: await status_cb(f"IMAGE: {ss}")
                    
                    try: await page.locator(".btn.green, .btn-primary").first.click(force=True, timeout=1000)
                    except: pass
                    await asyncio.sleep(1.5)

                f_btn = await page.get_by_text("Завершить").first
                if f_btn: await f_btn.click(force=True, timeout=2000)
                
                final_ss = "tmp/vnet_final_opt.png"
                await page.screenshot(path=final_ss)
                if ss_cb: await ss_cb(final_ss)
                return "SUCCESS", final_ss
            except Exception as e:
                return f"ERR: {str(e)[:30]}", None
            finally:
                await browser.close()

    async def solve_test(self, user_id, test_url, **kwargs):
        user = await self.db.get_user(user_id) or {"last_name": "Opti", "first_name": "Student"}
        return await self._solve_vnet(user, test_url, kwargs.get('status_callback'), kwargs.get('screenshot_callback'))
