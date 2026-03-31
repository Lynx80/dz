import asyncio
import re
import time
from playwright.async_api import async_playwright
from database.db import Database
from services.human_robot import HumanRobot

class ParserService:
    def __init__(self, db=None):
        self.db = db or Database()

    async def _solve_vnet(self, user, test_url, status_cb, ss_cb):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            robot = HumanRobot(page)
            try:
                if status_cb: await status_cb("[CMD] Starting Final v3.1 Text-Solver...")
                await page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                
                # Login
                inputs = await page.query_selector_all("input.input")
                if len(inputs) >= 3:
                    await robot.human_type(inputs[0], user.get('last_name', 'Student'))
                    await robot.human_type(inputs[1], user.get('first_name', 'Robot'))
                    await inputs[2].fill("11")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(12)

                # Get Data
                q_data = await page.evaluate("() => { let d = window.backend?.questions; try { return typeof d === 'string' ? JSON.parse(d) : d; } catch(e) { return {}; } }")
                qs = list(q_data.values()) if isinstance(q_data, dict) else (q_data or [])
                
                # NAVIGATION & TEXT SOLVE
                sidebar = await page.query_selector_all(".quest-num, .step__item, [class*='quest-num']")
                for i in range(min(len(qs), len(sidebar))):
                    if status_cb: await status_cb(f"[VNET] Step {i+1}")
                    await robot.human_click(sidebar[i]); await asyncio.sleep(3)
                    
                    q_info = qs[i]
                    correct_texts = [o.get('name', '') for o in q_info.get('options', []) if o.get('correct') or o.get('is_correct') == 1]
                    
                    # Fuzzy match on page
                    for c_txt in correct_texts:
                        clean_t = re.sub(r'[^a-яА-Яa-zA-Z0-9]', '', c_txt).lower()
                        if not clean_t: continue
                        
                        # Find all option containers
                        opts = await page.query_selector_all(".quest-item-option, label, .el-radio, .el-checkbox")
                        for opt_el in opts:
                            txt = await opt_el.inner_text()
                            if clean_t in re.sub(r'[^a-яА-Яa-zA-Z0-9]', '', txt).lower():
                                await robot.human_click(opt_el)
                                await asyncio.sleep(0.5); break
                    
                    # Next/Save
                    btn = await page.query_selector(".btn.green, .btn-primary, button:has-text('Далее')")
                    if btn: await robot.human_click(btn); await asyncio.sleep(1.5)

                # Final Finish
                f_btn = await page.query_selector("button:has-text('Завершить'), .btn-danger, .test-buttons .green")
                if f_btn: await robot.human_click(f_btn); await asyncio.sleep(4)
                
                ss = f"tmp/vnet_v31_{int(time.time())}.png"
                await page.screenshot(path=ss)
                if ss_cb: await ss_cb(ss)
                return "SUCCESS", ss
            except Exception as e:
                return f"ERR: {str(e)[:30]}", None
            finally:
                await browser.close()

    async def solve_test(self, user_id, test_url, **kwargs):
        user = await self.db.get_user(user_id) or {}
        return await self._solve_vnet(user, test_url, kwargs.get('status_callback'), kwargs.get('screenshot_callback'))
