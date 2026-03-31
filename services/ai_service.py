import logging
import json
import asyncio
import os
import aiohttp
import time
from aiohttp_socks import ProxyConnector

from config import GEMINI_API_KEYS, PROXY_URL

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.api_keys = [k for k in GEMINI_API_KEYS if k and k.strip()]
        self.key_index = 0
        self.proxy = PROXY_URL
        self.model = "gemini-2.5-flash" 
        # Примечание: В 2026 году модели 1.5 уже не поддерживаются, используем 2.5
        self.cooldowns = {k: 0 for k in self.api_keys}
        
    def _get_active_key(self):
        """Returns the next available key that is not in cooldown."""
        now = time.time()
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self.key_index]
            if now > self.cooldowns.get(key, 0):
                return key
            # Shift to next
            self.key_index = (self.key_index + 1) % len(self.api_keys)
        return None

    async def get_answer(self, question, options=None, image_b64=None):
        """Calls Gemini API to get the answer with rotation and error handling."""
        
        for attempt in range(len(self.api_keys)):
            key = self._get_active_key()
            if not key:
                logger.error("All Gemini API keys are in cooldown!")
                break
                
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
            
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
                    "inline_data": { "mime_type": "image/png", "data": image_b64 }
                })

            payload = {"contents": contents}
            
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            async with aiohttp.ClientSession(connector=connector) as session:
                try:
                    async with session.post(url, json=payload, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text_res = data['candidates'][0]['content']['parts'][0]['text']
                            # Очистка JSON от маркдауна и лишних символов
                            text_res = text_res.replace('```json', '').replace('```', '').strip()
                            try:
                                return json.loads(text_res)
                            except json.JSONDecodeError:
                                # Попытка извлечь JSON если вокруг есть текст
                                start = text_res.find('{')
                                end = text_res.rfind('}') + 1
                                if start != -1 and end != 0:
                                    return json.loads(text_res[start:end])
                                raise
                        elif resp.status == 429:
                            logger.warning(f"Gemini API key {key[:8]}... reached limit. Switching.")
                            self.cooldowns[key] = time.time() + 60
                            self.key_index = (self.key_index + 1) % len(self.api_keys)
                            continue
                        else:
                            error_text = await resp.text()
                            logger.error(f"Gemini API Error {resp.status} with key {key[:8]}...: {error_text}")
                            self.key_index = (self.key_index + 1) % len(self.api_keys)
                            continue
                except Exception as e:
                    logger.error(f"AI Error with key {key[:8]}...: {e}")
                    self.key_index = (self.key_index + 1) % len(self.api_keys)
                    continue

        return self._mock_answer(question, options)

    async def analyze_test_step(self, question, options=None):
        """Возвращает чистый текст правильного ответа."""
        res = await self.get_answer(question, options)
        if isinstance(res, dict):
            ans = res.get('answer', '')
            # Если это номер (1, 2, 3), пытаемся взять текст из options
            if isinstance(ans, int) and options and len(options) >= ans:
                return options[ans-1]
            return str(ans)
        return str(res)

    async def solve_vision_task(self, image_b64, context_info=""):
        """Specialized method for analyzing screenshots and providing click instructions."""
        prompt = f"""Твоя роль - эксперт по решению тестов (МЭШ/Мосрег). Анализируй скриншот.
{context_info}
Инструкции по типам заданий:
1. Квадраты в предложениях (Dropdown): Найди квадрат (placeholder) в тексте и нажми на него, чтобы открыть выбор. Если выбор уже открыт, нажми на ПРАВИЛЬНЫЙ вариант.
2. Связывание (Matching): Всегда нажимай ПАРАМИ. Сначала на кружок/слово слева, затем на соответствующий ему кружок/слово справа. 
   - Слева обычно английское слово, справа - перевод.
   - Для выполнения связывания нужно ДВА клика подряд в одном ответе 'actions'.
3. Обычный выбор: Нажми на текст или радиокнопку правильного ответа.
4. Кнопка 'Подтвердить' / 'Далее': Всегда добавляй клик по ней в конец списка 'actions', если задание выполнено.
5. Перетаскивание (Drag-and-Drop / Sorting): Если видишь стопку карточек (справа) и корзины (слева):
   - Используй тип действия {{"type": "drag", "x": 780, "y": 600, "end_x": 220, "end_y": 400, "label": "Текст"}}.
   - x, y: Центр карточки. end_x, end_y: Центр целевой зоны.

Координаты: относительные (0-1000). 0 - лево/верх, 1000 - право/низ.
Формат ответа JSON:
{{
  "task_type": "sorting | matching | single | multi | input",
  "actions": [
    {{"type": "drag", "x": 780, "y": 600, "end_x": 220, "end_y": 400, "label": "Слово"}}
  ],
  "is_final_step": true,
  "explanation": "краткое описание логики"
}}
"""
        return await self.get_answer(prompt, image_b64=image_b64)

    def _mock_answer(self, question, options):
        if options:
            return {"type": "SINGLE", "answer": 1, "confidence": 0.5, "explanation": "Mock fallback"}
        return {"type": "TEXT", "answer": "Не удалось связаться с ИИ", "confidence": 0, "explanation": "Fallback"}
