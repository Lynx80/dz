import asyncio
import json
import logging
from parser import ParserService

logging.basicConfig(level=logging.INFO)

async def test():
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyNTg0ODg0Iiwic2NwIjoib3BlbmlkIHByb2ZpbGUiLCJtc2giOiI3YzBiZTkwOC1mZTkwLTRhOTktODNlZC1hZWM0ZWNlNzk0OGQiLCJpc3MiOiJodHRwczpcL1wvYXV0aGVkdS5tb3NyZWcucnUiLCJyb2wiOiIiLCJzc28iOiIxMTkzNjgyMjA4IiwiYXVkIjoiMjoxIiwibmJmIjoxNzc0NTQ5NDUwLCJhdGgiOiJlc2lhIiwicmxzIjoiezE6WzIwOjI6W10sMzA6NDpbXSw0MDoxOltdLDE4MzoxNjpbXSwyMTE6MTk6W10sNTMzOjQ4OltdXX0iLCJyZ24iOiI1MCIsImV4cCI6MTc3NTM5NDIwOSwiaWF0IjoxNzc0NTQ5NDUwLCJqdGkiOiI1Yzc2OTA4Zi1jOTBlLTQwNmEtYjY5MC04ZmM5MGUxMDZhMjUifQ.YAXwDJHpggdR5nnJwaHM2Fqv8AK0pfdbZWOc-q7dDDp6E0zToa7DAxTajvkgQanjEy5HiGVKBU2zvXNOMdGZQ3lgsn6GXqlwbDxsGPD18Bd4fr-EIE2WlQyoc88J_4jdBU5CobBPSggXaGrLzheRU_u2hNV7x-OEzSZIUOQX2-aUNmWzyNWCkShzw_6XtIrlOLceWZQ32Cl4oaASmixHUb85JdQffBCTGmoEmwz2rTJdqvABpylm-VZSJm1H82_Fw8UvCXOQIllwUrIg0-aVkK6wjRUIEUYDNa82U86O1wMfJ-h-zpvIckMRAmCeVJAhYhdiQarMLmLELQ53FNfoQA"
    student_id = "2584884"
    mesh_id = "7c0be908-fe90-4a99-83ed-aec4ece7948d"
    date = "2026-03-26"
    
    parser = ParserService()
    # Manual ID injection for testing
    res = await parser.get_mosreg_schedule(token, student_id, date, mesh_id=mesh_id)
    print(f"Schedule found: {len(res)} items")
    for i, item in enumerate(res, 1):
        print(f"{i}. {item['time']} {item['subject']}")
    
    await parser.session.close()

if __name__ == "__main__":
    asyncio.run(test())
