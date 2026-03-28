# verify_fixes.py
import asyncio
import os
import aiohttp
import sys
from parser import ParserService
from bot import create_pid_file, remove_pid_file, PID_FILE

async def test_parser_session():
    print("Testing ParserService with shared session...")
    async with aiohttp.ClientSession() as session:
        parser = ParserService(session=session)
        # We don't have a real token here, but we can check if it uses the session correctly
        # and doesn't crash on initialization or basic calls.
        print("ParserService with shared session initialized.")
        
        # Test session reuse logic
        internal_session = await parser._get_session()
        assert internal_session is session
        print("Verified: ParserService uses the provided shared session.")

async def test_pid_logic():
    print("\nTesting PID file logic...")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    
    # Test 1: Successful creation
    assert create_pid_file() == True
    assert os.path.exists(PID_FILE)
    print("Test 1: PID file created successfully.")
    
    # Test 2: Collision detection (same process)
    # Note: Our current logic allows same process to "re-own" if it's the same PID, 
    # but the tasklist check might find itself. 
    # Let's see what happens.
    res = create_pid_file()
    print(f"Test 2: Collision detection result (same process): {res}")
    
    remove_pid_file()
    assert not os.path.exists(PID_FILE)
    print("Test 3: PID file removed successfully.")

async def main():
    try:
        await test_parser_session()
        await test_pid_logic()
        print("\nAll basic verifications passed!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
