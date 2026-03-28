import logging
import json
import asyncio
import os
import aiohttp
from aiohttp_socks import ProxyConnector

from config import GEMINI_API_KEY, PROXY_URL

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.proxy = PROXY_URL
        self.model = "gemini-1.5-flash-latest" 
        
    async def get_answer(self, question, options=None, image_b64=None):
        """Calls Gemini API to get the answer."""
        if not self.api_key or self.api_key == "MOCK_MODE":
            return self._mock_answer(question, options)
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        prompt = f"Ты помощник по решению школьных тестов. Отвечай строго в формате JSON.\nВопрос: {question}\n"
        if options:
            prompt += f"Варианты ответов:\n" + "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
            prompt += "\nВыбери номер правильного ответа (1, 2, 3...)."
        else:
            prompt += "\nДай краткий текстовый ответ."
            
        prompt += "\nФормат ответа JSON: {'answer': 1, 'confidence': 0.9, 'explanation': '...', 'type': 'SINGLE'}"
        
        parts = [{"text": prompt}]
        contents = [{"parts": parts}]
        
        if image_b64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": image_b64
                }
            })

        payload = {"contents": contents}
        
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status != 200:
                        logger.error(f"Gemini API Error {resp.status}: {await resp.text()}")
                        return self._mock_answer(question, options)
                        
                    data = await resp.json()
                    text_res = data['candidates'][0]['content']['parts'][0]['text']
                    # Очистка JSON от маркдауна
                    text_res = text_res.replace('```json', '').replace('```', '').strip()
                    return json.loads(text_res)
            except Exception as e:
                logger.error(f"AI Error: {e}")
                return self._mock_answer(question, options)

    def _mock_answer(self, question, options):
        # Fallback to mock logic
        if options:
            return {"type": "SINGLE", "answer": 1, "confidence": 0.5, "explanation": "Mock fallback"}
        return {"type": "TEXT", "answer": "Не удалось связаться с ИИ", "confidence": 0, "explanation": "Fallback"}
