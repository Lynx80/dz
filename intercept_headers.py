import asyncio
import json
from playwright.async_api import async_playwright

async def intercept():
    async with async_playwright() as p:
        # Use existing session if possible, or just log in
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Token from DB to try and set session
        token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NjI3NjQ0LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTI5NDkxMCwiaWF0IjoxNzc0NjI3NjQ0LCJqdGkiOiIxMWU0MmM3OS1lOWFjLTQ0OGItYTQyYy03OWU5YWNlNDhiNTIifQ.WjYpz-IyPFXKdvJpSLB9m8lvvuU2Ztx0lWzb0n6Sou0AoVtgi0ag5xD8y_i5wdIoOI8diyTd_4rZBd1Y0rWHFZK3bahT8oyW9YpwIGWAPIrithjCPvc3s6SAMBCVRM-mDUVYq6fIa-vLDl3PjKTo9duUoLe233IzYW1jAGYg3VZMAzIiRQrtF9H6XSngpAti7ECqqUuCtdghU2O4SlGeFuRRxa5GcpwRpjENdEjWOkDBlMA-mYIYy_gJlU7aepyvRp2u_530kF2GnZfbgja_N2chj7qmr__nZE2UWE-lUdSKl0wogfVmtQCJ8Solhdqrp96IA71N2R1_0pxZbox7ZQ"
        
        print(f"Setting local storage with token...")
        # Navigate to domain first to set storage
        await page.goto("https://myschool.mosreg.ru/")
        await page.evaluate(f"localStorage.setItem('access-token', '{token}')")
        await page.evaluate(f"localStorage.setItem('auth-token', '{token}')")
        
        # Intercept requests
        async def handle_request(request):
            if "api" in request.url or "schedule" in request.url or "diary" in request.url:
                if "static" not in request.url and "assets" not in request.url:
                    print(f"\n--- API REQUEST: {request.url} ---")
                    print(f"Headers: {json.dumps(dict(request.headers), indent=2)}")
        
        async def handle_response(response):
            if "api" in response.url and ("schedule" in response.url or "diary" in response.url):
                print(f"--- API RESPONSE: {response.url} | Status: {response.status} ---")
                try:
                    text = await response.text()
                    print(f"Body snippet: {text[:500]}")
                except: pass
        
        page.on("request", handle_request)
        page.on("response", handle_response)
        
        print("Navigating to Diary...")
        await page.goto("https://myschool.mosreg.ru/diary/schedules/day", wait_until="load")
        
        # Click around if needed to trigger fetches
        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(intercept())
