
import asyncio
import random
import math
from playwright.async_api import Page

class HumanRobot:
    """
    Класс для имитации человеческого поведения в браузере.
    Обходит защиту от роботов за счет плавных движений мыши и физических кликов.
    """
    
    def __init__(self, page: Page):
        self.page = page
        self.mouse = page.mouse
        self.current_pos = {"x": 0, "y": 0}

    async def move_mouse_smoothly(self, target_x: float, target_y: float, steps: int = None):
        """Перемещает мышь по кривой Безье к цели."""
        if steps is None:
            steps = random.randint(15, 30) # Рандомное количество шагов для имитации скорости
            
        start_x, start_y = self.current_pos["x"], self.current_pos["y"]
        
        # Генерируем 1-2 контрольные точки для кривой для "ломанности" движения
        control_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.8) + random.randint(-50, 50)
        control_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.8) + random.randint(-50, 50)
        
        for i in range(steps + 1):
            t = i / steps
            # Формула квадратичной кривой Безье
            x = (1 - t)**2 * start_x + 2 * (1 - t) * t * control_x + t**2 * target_x
            y = (1 - t)**2 * start_y + 2 * (1 - t) * t * control_y + t**2 * target_y
            
            await self.mouse.move(x, y)
            self.current_pos = {"x": x, "y": y}
            
            # Микро-задержка для имитации физического движения
            if i % 3 == 0:
                await asyncio.sleep(random.uniform(0.001, 0.005))

    async def human_click(self, selector_or_element, offset_jitter: int = 5):
        """Находит элемент и кликает в него с человеческой точностью."""
        target_x, target_y = None, None
        element = None
        
        # 1. Определяем координаты
        if isinstance(selector_or_element, dict) and 'x' in selector_or_element:
            box = selector_or_element
        else:
            element = selector_or_element
            if isinstance(selector_or_element, str):
                element = await self.page.wait_for_selector(selector_or_element, timeout=5000)
            
            if not element: return False
            box = await element.bounding_box()
            
        if not box: return False
        
        # 2. Умный скролл (только если нужно)
        if element:
            v = self.page.viewport_size
            if box['y'] < 50 or (box['y'] + box['height']) > (v['height'] - 50):
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.3, 0.6))
                box = await element.bounding_box() # Обновляем после скролла
            
        target_x = box['x'] + box['width'] / 2 + random.randint(-offset_jitter, offset_jitter)
        target_y = box['y'] + box['height'] / 2 + random.randint(-offset_jitter, offset_jitter)
        
        # 3. Физическое перемещение и клик
        await self.move_mouse_smoothly(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await self.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.mouse.up()
        return True

    async def human_type(self, selector, text: str, delay_range=(0.05, 0.15)):
        """Печатает текст с рандомными паузами между буквами."""
        await self.human_click(selector)
        await asyncio.sleep(0.5) # Пауза перед началом печати
        
        for char in text:
            await self.page.keyboard.type(char)
            await asyncio.sleep(random.uniform(*delay_range))
            
            # Шанс "запинки" при печати
            if random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.2, 0.5))

    async def scroll_smoothly(self, distance: int):
        """Плавная прокрутка страницы."""
        steps = random.randint(5, 10)
        step_dist = distance / steps
        for _ in range(steps):
            await self.page.mouse.wheel(0, step_dist + random.randint(-10, 10))
            await asyncio.sleep(random.uniform(0.05, 0.15))
