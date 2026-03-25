import os
import asyncio
import logging
from io import BytesIO

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WAITING_ACTION, WAITING_URL, WAITING_TOKEN, WAITING_LASTNAME, WAITING_FIRSTNAME, WAITING_CLASS, WAITING_AUTH = range(7)

MAIN_MENU_KBD = [
    ["📄 Получить ответы", "🤖 Авторешение"],
    ["💻 Мои ЦДЗ тесты", "⚙️ Настройки"],
    ["🆘 Помощь", "❌ Отмена"]
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _cleanup_browser(context)
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KBD, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привет! Я помогу тебе с решением ЦДЗ.\nВыбери действие в меню:",
        reply_markup=reply_markup
    )
    return WAITING_ACTION

async def handle_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "🤖 Авторешение" or text == "📄 Получить ответы":
        await update.message.reply_text("Введите URL страницы с тестом (МЭШ/ЦДЗ):", reply_markup=ReplyKeyboardRemove())
        return WAITING_URL
    elif text == "⚙️ Настройки":
        instruction = (
            "⚠️ **Мяу-мяу! Токен не загружен!** 😿\n\n"
            "🐱 Токен — это твой цифровой ключ! Он дает робокоту доступ к тестам! 🔑\n\n"
            "🔑 **Как получить токен:**\n\n"
            "1️⃣ Перейди по ссылке ниже.\n"
            "2️⃣ Введи логин и пароль от своего аккаунта.\n"
            "3️⃣ Скопируй токен со страницы (начинается с `eyJhb...`).\n"
            "4️⃣ Отправь его мне ответным сообщением! 🚀"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏙 Москва: Получить токен", url="https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh")],
            [InlineKeyboardButton("🌍 МО: 1. Войти", url="https://authedu.mosreg.ru/")],
            [InlineKeyboardButton("🌍 МО: 2. Получить токен", url="https://authedu.mosreg.ru/v2/token/refresh")],
            [InlineKeyboardButton("◀️ Вернуться в меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(instruction, parse_mode="Markdown", reply_markup=reply_markup)
        return WAITING_TOKEN
    elif text == "💻 Мои ЦДЗ тесты":
        await update.message.reply_text("Список ваших тестов пока пуст.")
        return WAITING_ACTION
    elif text == "🆘 Помощь":
        await update.message.reply_text("Этот бот помогает решать тесты ЦДЗ. Для начала нажмите 'Авторешение'.")
        return WAITING_ACTION
    elif text == "❌ Отмена":
        return await cancel(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню.")
        return WAITING_ACTION

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "main_menu":
        await _cleanup_browser(context)
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KBD, resize_keyboard=True)
        await query.message.reply_text("Вы вернулись в главное меню:", reply_markup=reply_markup)
        return WAITING_ACTION
    return WAITING_TOKEN

async def receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = update.message.text.strip()
    context.user_data["auth_token"] = token
    await update.message.reply_text("✅ Токен сохранен! Теперь введите URL теста:")
    return WAITING_URL


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    context.user_data["url"] = url
    await update.message.reply_text("Введите фамилию:")
    return WAITING_LASTNAME

async def receive_lastname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lastname"] = update.message.text.strip()
    await update.message.reply_text("Введите имя:")
    return WAITING_FIRSTNAME

async def receive_firstname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["firstname"] = update.message.text.strip()
    await update.message.reply_text("Класс или группа, например 4 «А»")
    return WAITING_CLASS

async def receive_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["classTxt"] = update.message.text.strip()
    url = context.user_data.get("url")

    await update.message.reply_text("Открываю страницу...")

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ru-RU",
        )
        page = await ctx.new_page()
        # Скрываем признаки автоматизации
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        context.user_data["playwright"] = playwright
        context.user_data["browser"] = browser
        context.user_data["ctx"] = ctx
        context.user_data["page"] = page

        await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
        
        # Если есть сохраненный токен, пробуем его применить (упрощенная логика)
        auth_token = context.user_data.get("auth_token")
        if auth_token:
            # Пытаемся добавить токен в localStorage или cookies в зависимости от платформы
            await page.evaluate(f"localStorage.setItem('auth_token', '{auth_token}')")
            # Для МЭШ часто используется кука CMS-SESSION
            await ctx.add_cookies([{"name": "CMS-SESSION", "value": auth_token, "url": url}])
            await page.reload(wait_until="domcontentloaded")
        
        if "videouroki.net/tests/" in url:
            # Заполняем форму
            try:
                await page.fill('input[name="lastname"]', context.user_data.get("lastname", ""))
                await page.fill('input[name="firstname"]', context.user_data.get("firstname", ""))
                await page.fill('input[name="classTxt"]', context.user_data.get("classTxt", ""))
                await page.click('input[value="Начать тест"]')
                await page.wait_for_timeout(3000)
                
                # Скриншот после входа в тест
                screen_start = await page.screenshot(full_page=False)
                await update.message.reply_photo(photo=BytesIO(screen_start), caption="Успешно зашел в тест! Начинаю решать...")

                import re
                for i in range(1, 11):
                    # Пробуем выбрать первый вариант ответа на текущей странице 
                    try:
                        opt = page.locator(".el-radio, .el-checkbox, label:has(input)").first
                        if await opt.count() > 0:
                            await opt.click(force=True)
                        else:
                            # Если это текстовое поле ввода
                            inp = page.locator('input.el-input__inner').first
                            if await inp.count() > 0:
                                await inp.fill("А")
                    except Exception:
                        pass
                    
                    # Делаем скриншот с ответом
                    screen_q = await page.screenshot(full_page=False)
                    await update.message.reply_photo(photo=BytesIO(screen_q), caption=f"Вопрос {i}: Ответ выбран.")
                    
                    # Нажимаем Далее/Сохранить
                    try:
                        btn = page.locator('button, .btn, a.btn').filter(has_text=re.compile(r"Далее|Ответить|Сохранить", re.IGNORECASE)).first
                        if await btn.count() > 0:
                            await btn.click()
                        else:
                            # Если кнопок нет, возможно конец теста
                            break
                    except Exception:
                        break
                        
                    await page.wait_for_timeout(2000)
                
                # Итоговый скриншот
                await page.wait_for_timeout(2000)
                screen_end = await page.screenshot(full_page=False)
                await update.message.reply_photo(photo=BytesIO(screen_end), caption="Завершил 10 шагов!")
                
            except Exception as e:
                await update.message.reply_text(f"Ошибка в процессе прохождения теста: {e}")
                
            # Завершаем диалог
            return ConversationHandler.END

        # Для других сайтов - логика QR-кода
        try:
            await page.wait_for_selector("img, canvas", timeout=15_000)
        except Exception:
            pass

        qr_image_data = await _find_qr_image(page)

        if qr_image_data is None:
            qr_image_data = await page.screenshot(full_page=False)
            caption = "QR-код не найден — скриншот страницы.\nОтсканируйте QR-код для авторизации"
        else:
            caption = "Отсканируйте этот QR-код для авторизации"

        await update.message.reply_photo(
            photo=BytesIO(qr_image_data),
            caption=caption,
        )
        await update.message.reply_text(
            "Жду подтверждения авторизации. Когда войдёте — отправьте /authorized"
        )
        return WAITING_AUTH

    except PlaywrightTimeout:
        await update.message.reply_text(
            "⚠️ Таймаут: страница не загрузилась за 45 секунд. Проверьте URL и попробуйте снова /start"
        )
        await _cleanup_browser(context)
        return ConversationHandler.END

    except Exception as e:
        logger.exception("Ошибка при открытии страницы")
        await update.message.reply_text(
            f"❌ Ошибка при открытии страницы: {e}\n\nПопробуйте снова /start"
        )
        await _cleanup_browser(context)
        return ConversationHandler.END


async def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✅ Авторизация принята! Можно продолжать.")
    # Браузер остаётся открытым для дальнейшей работы с тестом
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _cleanup_browser(context)
    await update.message.reply_text("Сессия сброшена. Для начала отправьте /start")
    return ConversationHandler.END


async def _find_qr_image(page) -> bytes | None:
    """
    Ищет QR-код на странице:
    1. img с src содержащим 'qr'
    2. img с alt/class содержащим 'qr'
    3. canvas-элемент (QR часто рендерится через canvas)
    Возвращает bytes изображения или None.
    """
    # Ищем <img> похожий на QR по атрибутам
    selectors = [
        "img[src*='qr' i]",
        "img[alt*='qr' i]",
        "img[class*='qr' i]",
        "img[id*='qr' i]",
        "canvas[class*='qr' i]",
        "canvas[id*='qr' i]",
    ]
    for selector in selectors:
        element = await page.query_selector(selector)
        if element:
            try:
                return await element.screenshot()
            except Exception:
                continue

    # Если ничего не нашли — берём первый заметный canvas
    canvas = await page.query_selector("canvas")
    if canvas:
        try:
            return await canvas.screenshot()
        except Exception:
            pass

    return None


async def _cleanup_browser(context: ContextTypes.DEFAULT_TYPE):
    """Закрывает browser и playwright если они открыты."""
    browser = context.user_data.pop("browser", None)
    playwright = context.user_data.pop("playwright", None)
    context.user_data.pop("ctx", None)
    context.user_data.pop("page", None)

    if browser:
        try:
            await browser.close()
        except Exception:
            pass
    if playwright:
        try:
            await playwright.stop()
        except Exception:
            pass


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file")
        return

    # Увеличиваем таймауты для стабильности при плохом соединении
    app = Application.builder().token(token).connect_timeout(30).read_timeout(30).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_click)
            ],
            WAITING_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url)
            ],
            WAITING_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token),
                CallbackQueryHandler(handle_callback)
            ],
            WAITING_LASTNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_lastname)
            ],
            WAITING_FIRSTNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_firstname)
            ],
            WAITING_CLASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_class)
            ],
            WAITING_AUTH: [
                CommandHandler("authorized", authorized),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
