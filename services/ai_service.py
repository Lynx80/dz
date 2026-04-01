import logging
import json
import asyncio
import aiohttp
import time
from config import GEMINI_API_KEYS, PROXY_URL

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.api_keys = [k for k in GEMINI_API_KEYS if k and k.strip()]
        self.key_index = 0
        self.model = "gemini-2.0-flash" 
        self._cache = {} # TOKEN SAVER: Store answers for identical questions

    async def get_answer(self, question, options=None):
        """Calls Gemini API with caching to save tokens."""
        cache_key = f"{question}_{str(options)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        key = self.api_keys[self.key_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
        
        # Lean prompt
        prompt = f"Q: {question}\nOpts: {options}\nAns in JSON: {{'answer': str/int, 'conf': float}}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        res = json.loads(text.replace('```json', '').replace('```', '').strip())
                        self._cache[cache_key] = res
                        return res
            except: pass
        return {"answer": options[0] if options else "No AI response", "conf": 0}

    async def analyze_test_step(self, question, options=None):
        res = await self.get_answer(question, options)
        ans = res.get('answer', '')
        if isinstance(ans, int) and options and len(options) >= ans:
            return options[ans-1]
        return str(ans)
