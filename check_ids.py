import aiohttp
import asyncio
import json

async def test():
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NTQ5NDUwLCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTM5NDIwOSwiaWF0IjoxNzc0NTQ5NDUwLCJqdGkiOiI1Yzc2OTA4Zi1jOTBlLTQwNmEtYjY5MC04ZmM5MGUxMDZhMjUifQ.YAXwDJHpggdR5nnJwaHM2Fqv8AK0pfdbZWOc-q7dDDp6E0zToa7DAxTajvkgQanjEy5HiGVKBU2zvXNOMdGZQ3lgsn6GXqlwbDxsGPD18Bd4fr-EIE2WlQyoc88J_4jdBU5CobBPSggXaGrLzheRU_u2hNV7x-OEzSZIUOQX2-aUNmWzyNWCkShzw_6XtIrlOLceWZQ32Cl4oaASmixHUb85JdQffBCTGmoEmwz2rTJdqvABpylm-VZSJm1H82_Fw8UvCXOQIllwUrIg0-aVkK6wjRUIEUYDNa82U86O1wMfJ-h-zpvIckMRAmCeVJAhYhdiQarMLmLELQ53FNfoQA"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Mes-Subsystem": "familyweb",
        "X-Mes-Role": "student"
    }
    
    async with aiohttp.ClientSession() as session:
        # Check profiles
        async with session.get("https://myschool.mosreg.ru/acl/api/users/profile_info", headers=headers) as resp:
            print(f"Profile Info Status: {resp.status}")
            data = await resp.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
        # Check family profile
        async with session.get("https://authedu.mosreg.ru/api/family/mobile/v1/profile", headers=headers) as resp:
            print(f"Family Profile Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test())
