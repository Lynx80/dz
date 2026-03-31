import asyncio
import os
import logging
import random
import time
import re
from playwright.async_api import async_playwright
from database.db import Database
from services.human_robot import HumanRobot

logger = logging.getLogger(__name__)

class ParserService:
    def __init__(self, db=None):
        from services.ai_service import AIService
        from services.answer_finder import AnswerFinder
        self.db = db or Database()
        self.ai = AIService()
        self.finder = AnswerFinder(self.ai)

    async def _solve_videouroki(self, user, test_url, status_cb, ss_cb):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            robot = HumanRobot(page)
            try:
                if status_cb: await status_cb("[WEB] Starting Videouroki v2.8 (Sidebar Navigator)...")
                await page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                
                # 1. Login
                inputs = await page.query_selector_all("input.input")
                if len(inputs) >= 3:
                    if status_cb: await status_cb("[AUTH] Login procedure...")
                    await robot.human_type(inputs[0], user.get('last_name', 'Student'))
                    await robot.human_type(inputs[1], user.get('first_name', 'Robot'))
                    await inputs[2].fill("11")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(12)

                # 2. Extract Data
                q_data = await page.evaluate('''() => {
                    let d = window.backend && window.backend.questions;
                    if (typeof d === "string") { try { d = JSON.parse(d); } catch(e) {} }
                    return d;
                }''')
                if not q_data: return "ERROR: NO_DATA", None
                qs = list(q_data.values()) if isinstance(q_data, dict) else q_data

                # 3. Solve (Sidebar-Navigator Strategy)
                # We iterate through ALL sidebar items one by one
                sidebar_items = await page.query_selector_all(".quest-num, .step__item")
                if not sidebar_items:
                    # Alternative finder for sidebar
                    sidebar_items = await page.query_selector_all("[class*='quest'][class*='item']")
                
                # If we have 10 items in sidebar, we solve 10 times
                total_qs = min(len(qs), len(sidebar_items))
                if status_cb: await status_cb(f"[DATA] Questions: {total_qs}")

                for i in range(total_qs):
                    # Click sidebar item to go to question i
                    if status_cb: await status_cb(f"[NAV] Going to Question {i+1}")
                    await robot.human_click(sidebar_items[i])
                    await asyncio.sleep(3)

                    q_info = qs[i]
                    # Log solve
                    if status_cb: await status_cb(f"[SOLVE] Resolving Q{i+1}")
                    
                    # Logic: click by option index
                    opts = q_info.get('options', [])
                    correct_indices = [idx for idx, o in enumerate(opts) if o and (o.get('correct') or o.get('is_correct') == 1)]
                    
                    # Click options by index in the current question area
                    radio_btns = await page.query_selector_all(".quest-item-option input, .el-radio, .el-checkbox, label")
                    if len(radio_btns) >= len(opts):
                        for c_idx in correct_indices:
                            if c_idx < len(radio_btns):
                                await robot.human_click(radio_btns[c_idx]); await asyncio.sleep(0.5)
                    else:
                        # Fallback to Text-Click
                        for c_idx in correct_indices:
                            txt = opts[c_idx].get('name', '')
                            try: await page.click(f"text='{txt[:20]}'", timeout=2000)
                            except: pass

                    # Optional: click "Next" just to trigger any callbacks, but not strictly needed
                    next_btn = await page.query_selector(".btn.green, .btn-primary, button:has-text('Далее')")
                    if next_btn: await robot.human_click(next_btn); await asyncio.sleep(2)
                    # Modal save
                    modal = await page.query_selector(".el-button--primary, .modal-footer .green")
                    if modal: await robot.human_click(modal); await asyncio.sleep(2)

                # Final Submit
                finish_btn = await page.query_selector("button:has-text('Завершить'), .btn-danger, .test-buttons .red")
                if finish_btn: await robot.human_click(finish_btn); await asyncio.sleep(5)
                
                final_ss = f"tmp/vnet_final_{int(time.time())}.png"
                await page.screenshot(path=final_ss, full_page=True)
                if ss_cb: await ss_cb(final_ss)
                return "SUCCESS", final_ss
                
            except Exception as e:
                return f"ERROR: {str(e)[:40]}", None
            finally:
                await browser.close()

    async def solve_test(self, user_id, test_url, **kwargs):
        user = await self.db.get_user(user_id)
        if not user: user = {"last_name": "Student", "first_name": "Robot", "grade": "11"}
        if "videouroki.net" in test_url:
            return await self._solve_videouroki(user, test_url, kwargs.get('status_callback'), kwargs.get('screenshot_callback'))
        return "UNKNOWN", None
