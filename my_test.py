import aiohttp, asyncio

async def test():
    token = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NDQzNzM5LCJhdGgiOiJlc2lhIiwicmxzIjoie3sxOlsyMDoyOltdLDMwOjQ6W10sNDA6MTpbXSwxODM6MTY6W10sMjExOjE5OlsyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTMwNzE2OSwiaWF0IjoxNzc0NDQzNzM5LCJqdGkiOiJkODhkMGIxMi0yMDkyLTQzMjQtOGQwYi0xMjIwOTI1MzI0OWEifQ.YSSiL1RjgMDGktZevTwbbG0PwGOVjsRLSw5EU3zI_aay7xeTygtSbUtjWOPVZsDgJeKY3GfZHLBFBEklOVFpCnKJc1g__mlvS-XVES9Bzv62FzDa3fnAAihFLcAYLd7TmJE47dwm5Llh9BY-uoAysfMpwPimRz9HZe9ZqDK8vXcNLnU3p2pNMVg3zdbdcaYvhBcsjWhzx1O-B2PThTXVF3_CKheM_ofZ9Ae6VYxuXA5CFi6x-z068h8fjQA4cH3itafAKteYhivRCbN0Rp8wm5-kwqqGvtKfxtspuUAQ7D1ehrjDBDAHh9fA5nsGcJ_vuxAPHIJ7vYDufXpP1vA6lg'
    async with aiohttp.ClientSession() as s:
        async with s.get('https://school.mos.ru/api/family/v1/profile', headers={'Authorization': 'Bearer ' + token}) as r:
            print(r.status, await r.text()[:200])

asyncio.run(test())
