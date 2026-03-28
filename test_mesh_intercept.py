import asyncio
import json
import os
from playwright.async_api import async_playwright

async def run():
    # Token for user 229041009
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjMxNTE4LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjMxNTE4LCJqdGkiOiJkNTg3ZWRjZi1jOGM1LTQ5YzMtODdlZC1jZmM4YzVjOWMzNWUifQ.g0M__Nw8TIN0rVPP3UFAZpwRZMlH7tJLqZczHTbSauimSvrxNKyJ61El_eroTW_iVdS3A6jtRfs5JHvfM0FVTg7679aIXO-mGE-_CDSWhFYClJKnd8Cf2iWqQR2u_Z8Ht2FUjQt-LM_-EX_bhBcrZJ5bcBSFGV9UfzR_Blb6YjNA5u7uFTu_ATWMfUTYz5ZGEdpfA3V4iEBAQB9l9ogYdrhmu6jTI8G9mC22SFZeUHZoTSMmyWoa2Nn8UxCuGDwLhMyvFkIjfn42I_3QkTvvFTHO6a7L3GpZUd4T_DvIT90uVA_4Pgm43dvuMHnvP22b235jigvfgd0VzxjG74Yg0A"
    
    # URL for a MESH test found in today's schedule
    target_url = "https://uchebnik.mos.ru/exam/challenge/128804041?activityId=https%3A%2F%2Fuchebnik.mos.ru%2Fexam%2Fchallenge%2F128804041&actor=%7B%22objectType%22%3A%22Agent%22%2C%22account%22%3A%7B%22name%22%3A%2250%3A7c0be908-fe90-4a99-83ed-aec4ece7948d%22%7D%7D&authurl=https%3A%2F%2Fauthedu.mosreg.ru&context=eyJhbGciOiJIUzI1NiJ9.eyJ3dCI6IjEiLCJ3dGkiOjkwOTg5ODEzLCJwaWQiOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJkdCI6MTc3NDYzMjQxMTU5NiwibWkiOiJlOWI4ZDZkZi1mYmU3LTMzY2MtYTA3Zi1hMTE4Mjg2ZDJjMjUifQ.3VHpz-up_IbNAuwz64BHu9AZ_9mdHnHWPkUZfcsEq2I&endpoint=https%3A%2F%2Fmyschool.mosreg.ru%2Flrs-dhw%2F&fetch=https%3A%2F%2Fmyschool.mosreg.ru%2Flrs-dhw%2F%2Ftoken%2Ffetch%2F383d7f4ff2cdd056f5fc810dfe208489&registration=2131ca50-5da6-4fda-9da0-abcbd7c372e6&role=student&utm_campaign=1&utm_medium=lesson&utm_source=familyw"
    
    print(f"Starting interception for: {target_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        intercepted_count = 0

        async def handle_response(response):
            nonlocal intercepted_count
            url = response.url
            if "application/json" in (response.headers.get("content-type") or "").lower():
                try:
                    text = await response.text()
                    data = json.loads(text)
                    
                    serialized_data = json.dumps(data).lower()
                    # Look for questions or answers
                    if any(kw in serialized_data for kw in ["answer", "correct", "question", "task", "option", "score"]):
                        intercepted_count += 1
                        print(f"!!! Captured TEST DATA JSON #{intercepted_count} from: {url[:100]}...")
                        output_file = f"intercepted_resp_{intercepted_count}.json"
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump({"url": url, "data": data}, f, ensure_ascii=False, indent=2)
                except:
                    pass

        page.on("response", handle_response)
        
        # 1. Login (Optional, then navigate)
        login_url = f"https://myschool.mosreg.ru/login/token?token={token}"
        print("Logging in (ensuring session)...")
        await page.goto(login_url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # 2. Go to target test page
        print(f"Navigating to direct test URL...")
        await page.goto(target_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(15)
        
        # Screenshot to see the state
        await page.screenshot(path="poc_test_loaded.png")
        print("Screenshot saved to poc_test_loaded.png")
        
        # 3. Final wait for background data
        await asyncio.sleep(15)
        
        print(f"Finished. Total TEST DATA intercepted: {intercepted_count}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
