import asyncio
import aiohttp
import json

async def main():
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NDQ5MTc3LCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTMwNzE2OSwiaWF0IjoxNzc0NDQ5MTc3LCJqdGkiOiI2NTkzODRiOS1hNTlkLTRiYmItOTM4NC1iOWE1OWRlYmJiMGEifQ.RAI7yTucxwqFqbeKX9hhPmlczhNLZcDtCBhisroemKOORJfzJGhMj1waflm5MyifFS_t03UJog63ersTUjIeOAgyW4AjXm-or6CHUx9RKmlDQ1lh1imL2mkmYex0wfzwBPZ70AZPuscSplbK9uuxoVj1WXp-iY0q9IzSMdf6iYZoh0R5zU9ditvCGViLDTLrJdAARiclHi19-MTDWKYQ0kng6S3CG71veG8sxettoY2Pqs-1zytDpTdNGBBJHKgqSeGH5_NviXy4JZ5da5C7Flro_sqJ9dokKIezj4kAzueEql2PgPWwB-Yik6lysNqwDJpEK6jCet0XOJ7HJtqleQ"
    
    async with aiohttp.ClientSession() as s:
        # Check standard OAuth endpoint for Desktop Apps
        print("1. Trying auth at login.school.mosreg.ru proxy endpoint...")
        resp = await s.post('https://login.school.mosreg.ru/login', data={'token': token}, allow_redirects=False)
        print("login.school.mosreg.ru:", resp.status, resp.headers)
        
        # Check if authedu gives a token endpoint
        print("2. Trying token info on api.school.mosreg.ru with Authorization")
        resp = await s.get('https://api.school.mosreg.ru/v2.0/users/me', headers={'Authorization': f'Bearer {token}'})
        print("Authorization Bearer API:", resp.status)
        try:
            print(await resp.text())
        except Exception:
            pass

asyncio.run(main())
