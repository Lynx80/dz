"""
Решатель тестов videouroki.net
Запуск: python3 videouroki_solver.py <URL>
"""
import asyncio, sys, os, re, json, base64, httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
URL = sys.argv[1] if len(sys.argv) > 1 else "https://videouroki.net/tests/939872999/"

_keys_raw = os.getenv("GEMINI_API_KEYS", "")
GEMINI_KEYS = [k.strip() for k in _keys_raw.split(",") if k.strip()]
if not GEMINI_KEYS:
    GEMINI_KEYS = [os.getenv("GEMINI_API_KEY")]
_key_index = 0

def _gemini_url():
    return f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEYS[_key_index]}"

# ── Gemini (только текст, без скриншотов) ─────────────────────────────────────
async def ask(prompt: str, image_url: str = None) -> dict:
    global _key_index
    parts = [{"text": prompt}]
    if image_url:
        if image_url.startswith("//"): image_url = "https:" + image_url
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(image_url)
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(r.content).decode()}})

    for attempt in range(len(GEMINI_KEYS) * 3):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(_gemini_url(), json={"contents": [{"parts": parts}]})
        if r.status_code == 429:
            next_key = (_key_index + 1) % len(GEMINI_KEYS)
            print(f"   [429] ключ {_key_index+1}/{len(GEMINI_KEYS)} исчерпан → переключаю на ключ {next_key+1}")
            _key_index = next_key
            await asyncio.sleep(2)
            continue
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r'\{.*\}', re.sub(r'```json|```', '', raw), re.DOTALL)
        if not m: raise ValueError(f"Не JSON: {raw[:100]}")
        return json.loads(m.group())
    raise RuntimeError("Gemini: все ключи исчерпаны")

# ── Получить все вопросы из Vue $data ─────────────────────────────────────────
GET_QUESTIONS_JS = """() => {
    function findVue(el) {
        if (el.__vue__) return el.__vue__;
        for (const c of el.children||[]) { const v=findVue(c); if(v) return v; }
    }
    const vm = findVue(document.body);
    const child = vm && vm.$children[0];
    if (!child) return null;
    try { return JSON.parse(JSON.stringify(child.$data.questions)); } catch(e) { return null; }
}"""

# ── Установить ответ через Vue ────────────────────────────────────────────────
async def vue_set_answer(page, answer_ids):
    """Устанавливает ответ напрямую через Vue $data.answers и помечает вопрос выполненным."""
    await page.evaluate(f"""() => {{
        function findVue(el) {{
            if (el.__vue__) return el.__vue__;
            for (const c of el.children||[]) {{ const v=findVue(c); if(v) return v; }}
        }}
        const vm = findVue(document.body);
        const child = vm && vm.$children[0];
        if (!child) return;
        child.$data.answers = {json.dumps(answer_ids)};
    }}""")
    await page.wait_for_timeout(200)

# ── Парсинг HTML вопроса ──────────────────────────────────────────────────────
def strip_html(html):
    return re.sub(r'<[^>]+>', '', html).strip()

def get_img_url(html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None

# ── Решение по типу ───────────────────────────────────────────────────────────
async def solve(q: dict) -> list:
    """Возвращает список answer_id для данного вопроса."""
    desc = strip_html(q['description'])
    img_url = get_img_url(q['description'])
    qtype = q['type']
    answers = q['answers']

    # type 1 — radio (один ответ)
    if qtype == 1:
        opts = "\n".join(f"{i}. {a['text']}" for i,a in enumerate(answers))
        result = await ask(
            f"Вопрос: {desc}\nВарианты:\n{opts}\n\nJSON: {{\"index\": N}}",
            img_url
        )
        return [answers[result['index']]['id']]

    # type 2 — checkbox (несколько)
    elif qtype == 2:
        opts = "\n".join(f"{i}. {a['text']}" for i,a in enumerate(answers))
        result = await ask(
            f"Вопрос: {desc}\nВарианты (несколько правильных):\n{opts}\n\nJSON: {{\"indices\": [0,1,...]}}"
        )
        return [answers[i]['id'] for i in result['indices']]

    # type 3 — текстовый ввод
    elif qtype == 3:
        result = await ask(f"Вопрос: {desc}\nОтвет коротко. JSON: {{\"answer\": \"текст\"}}", img_url)
        return [result['answer']]  # строка

    # type 4 — matching (сопоставление)
    elif qtype == 4:
        # annotation — левые элементы (что сопоставляем)
        left = []
        if q.get('annotation'):
            try:
                ann = json.loads(q['annotation'])
                left = [strip_html(a['text']) for a in ann]
            except: pass
        opts = "\n".join(f"{i+1}. {a['text']}" for i,a in enumerate(answers))
        left_str = "\n".join(f"{i+1}. {t}" for i,t in enumerate(left))
        result = await ask(
            f"Вопрос: {desc}\nЛевая сторона (что сопоставляем):\n{left_str}\n"
            f"Правая сторона (варианты ответов):\n{opts}\n"
            f"Сопоставь каждый левый элемент с правым. JSON: {{\"pairs\": [[left_i, right_i], ...]}}"
        )
        # Возвращаем пары [left_index, right_answer_id]
        return [(p[0], answers[p[1]]['id']) for p in result['pairs']]

    # type 6 — true/false (да/нет для каждого утверждения)
    elif qtype == 6:
        stmts = "\n".join(f"{i+1}. {a['text']}" for i,a in enumerate(answers))
        result = await ask(
            f"Вопрос: {desc}\nУтверждения:\n{stmts}\n"
            f"Для каждого: Правда или Ложь. JSON: {{\"answers\": [true, false, ...]}}"
        )
        # true/false маппится на answer id
        return [(a['id'], result['answers'][i]) for i,a in enumerate(answers)]

    return []

# ── Клик по ответу в браузере ──────────────────────────────────────────────────
async def click_answer(page, q: dict, answer_data):
    qtype = q['type']

    if qtype == 1:  # radio — кликаем label с нужным текстом
        ans_id = answer_data[0]
        ans_text = next(a['text'] for a in q['answers'] if a['id'] == ans_id)
        labels = await page.query_selector_all('.el-radio__label')
        for label in labels:
            t = (await label.inner_text()).strip()
            if ans_text in t or t in ans_text:
                await label.click()
                print(f"   ✓ radio: {ans_text}")
                return
        # fallback — по позиции
        idx = next(i for i,a in enumerate(q['answers']) if a['id'] == ans_id)
        await labels[idx].click()

    elif qtype == 2:  # checkbox
        for ans_id in answer_data:
            ans_text = next(a['text'] for a in q['answers'] if a['id'] == ans_id)
            labels = await page.query_selector_all('.el-checkbox__label')
            for label in labels:
                t = (await label.inner_text()).strip()
                if ans_text in t or t in ans_text:
                    await label.click()
                    await page.wait_for_timeout(100)
                    print(f"   ✓ checkbox: {ans_text}")
                    break

    elif qtype == 3:  # text input
        inp = await page.query_selector('input.w75, textarea')
        if inp:
            await inp.fill(str(answer_data[0]))
            print(f"   ✓ text: {answer_data[0]}")

    elif qtype == 4:  # matching — dropdown selects
        selects = await page.query_selector_all('.select__item:not(.select__bool) .el-input__inner')
        for left_idx, right_ans_id in answer_data:
            right_text = next(a['text'] for a in q['answers'] if a['id'] == right_ans_id)
            # Найдём номер ответа в dropdown
            if left_idx - 1 < len(selects):
                await selects[left_idx - 1].click()
                await page.wait_for_timeout(500)
                opts = await page.query_selector_all(
                    ".el-select-dropdown:not([style*='display: none']) li.el-select-dropdown__item span"
                )
                for opt in opts:
                    t = (await opt.inner_text()).strip()
                    if t == str(left_idx):  # номер позиции
                        await opt.click()
                        print(f"   ✓ match [{left_idx}] → {right_text}")
                        break
                else:
                    await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)

    elif qtype == 6:  # true/false dropdowns
        blocks = await page.query_selector_all('.select__bool')
        for ans_id, is_true in answer_data:
            ans_text = next(a['text'] for a in q['answers'] if a['id'] == ans_id)
            target = "Да" if is_true else "Нет"
            idx = next(i for i,a in enumerate(q['answers']) if a['id'] == ans_id)
            if idx < len(blocks):
                inp = await blocks[idx].query_selector('.el-input__inner')
                if inp:
                    await inp.click()
                    await page.wait_for_timeout(500)
                    opts = await page.query_selector_all(
                        ".el-select-dropdown:not([style*='display: none']) li.el-select-dropdown__item span"
                    )
                    for opt in opts:
                        if (await opt.inner_text()).strip() == target:
                            await opt.click()
                            print(f"   ✓ {ans_text[:40]} → {target}")
                            break
                    else:
                        await page.keyboard.press("Escape")
                    await page.wait_for_timeout(300)

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    print(f"▶ {URL}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox", "--start-maximized"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}, locale="ru-RU"
        )
        page = await ctx.new_page()

        await page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.fill('input[name=lastname]', 'Иванов')
        await page.fill('input[name=firstname]', 'Иван')
        await page.fill('input[name=classTxt]', '11 А')
        await page.click('input[type=submit]')
        await page.wait_for_timeout(3000)
        print("→ Тест начат\n")

        for num in range(1, 100):
            btn = await page.query_selector('.test_main__next button.btn')
            if not btn:
                break

            # Получаем текущий вопрос из Vue
            questions = await page.evaluate(GET_QUESTIONS_JS)
            if not questions:
                print("[!] Вопросы не найдены")
                break

            # Текущий вопрос — первый не завершённый
            q = next((x for x in questions if not x.get('complite')), None)
            if not q:
                break

            desc = strip_html(q['description'])
            print(f"[{num}] type={q['type']} | {desc[:70]}")

            try:
                answer_data = await solve(q)
                await click_answer(page, q, answer_data)
            except Exception as e:
                print(f"   [!] {e}")

            await page.wait_for_timeout(400)
            btn = await page.query_selector('.test_main__next button.btn')
            if btn:
                await btn.click()
                await page.wait_for_timeout(1500)
            else:
                break

        await page.wait_for_timeout(2000)
        body = await page.inner_text('body')
        m = re.search(r'(\d+\s*(?:из|баллов)[^.\n]{0,30})', body)
        print(f"\n✅ {m.group() if m else 'Тест завершён — смотри браузер'}")
        print("Браузер закроется через 60 сек...")
        await asyncio.sleep(60)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
