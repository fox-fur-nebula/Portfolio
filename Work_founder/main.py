import os
import asyncio
import hashlib
import logging
from aiogram import loggers as aiogram_loggers
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Type
import aiosqlite
from aiogram import Bot, Dispatcher, Router, exceptions
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Установите переменную окружения BOT_TOKEN")

DB_PATH = "jobs.db"
FETCH_INTERVAL = 15 * 60
DETAILS_LIMIT = 20
PAGES_LIMIT = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("jobs-bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

class ColorLanguageLogger:
    class LanguageFormatter(logging.Formatter):
        RESET = "\033[0m"
        GRAY = "\033[38;2;200;200;200m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        translations = {
            "Start polling": "Запуск получения обновлений...",
            "Run polling for bot": "Запущено получение обновлений для бота",
            "Update id": "Обновление id",
            "Polling stopped": "Получение обновлений остановлено",
            "Запуск цикла парсинга...": "Начало нового цикла поиска вакансий...",
        }
        def format(self, record):
            msg = record.getMessage()
            for eng, rus in self.translations.items():
                if eng in msg:
                    msg = msg.replace(eng, rus)
            if record.levelno >= logging.ERROR:
                date_color = self.RED
                level_color = self.RED
                colon_color = self.RED
                msg_color = self.RED
            elif record.levelno >= logging.WARNING:
                date_color = self.YELLOW
                level_color = self.YELLOW
                colon_color = self.YELLOW
                msg_color = self.YELLOW
            else:
                date_color = self.GRAY
                level_color = self.GRAY
                colon_color = self.GRAY
                msg_color = self.GRAY

            date_str = f"{date_color}{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}{self.RESET}"
            level_str = f"{level_color}{record.levelname}{self.RESET}"
            colon_str = f"{colon_color}:{self.RESET}"
            msg_str = f"{msg_color}{msg}{self.RESET}"
            return f"{date_str} {level_str}{colon_str} {msg_str}"
    logging.getLogger().handlers.clear()
    formatter = LanguageFormatter()
    for logger_name in (
        "aiogram",
        aiogram_loggers.event.name,
        aiogram_loggers.dispatcher.name,
        "jobs-bot",
    ):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

# ================= ДАННЫЕ =================
def make_job_id(source: str, description: str) -> str:
    normalized_desc = " ".join(description.lower().strip().split())
    return hashlib.sha256(f"{source}|{normalized_desc}".encode()).hexdigest()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS subscribers(
                user_id INTEGER PRIMARY KEY
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS seen_jobs(
                id TEXT PRIMARY KEY,
                source TEXT,
                link TEXT,
                title TEXT,
                first_seen TEXT
        )""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_seen_first_seen ON seen_jobs(first_seen)")
        await db.commit()

async def job_seen(source: str, description: str, title: str) -> bool:
    jid = make_job_id(source, description)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM seen_jobs WHERE id = ?", (jid,))
        if await cur.fetchone():
            return True
        await db.execute(
            "INSERT INTO seen_jobs (id, source, link, title, first_seen) VALUES (?, ?, ?, ?, ?)",
            (jid, source, "", title[:100], datetime.now(timezone.utc).isoformat())
        )
        await db.commit()
        logger.info(f"Добавлена новая вакансия: {title[:50]}...")
        return False

async def get_subscribers() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM subscribers") as cur:
            subscribers = [row[0] async for row in cur]
    return subscribers


# ================= ПОИСК =================
class WorkUA:
    name = "work.ua"
    start_url = "https://www.work.ua/jobs-it-industry-it/?advs=1&sort=date&days=122&language=1+41&language_level=1-83+1-84+41-22836"

    async def run(self) -> List[Dict]:
        logger.info(f"Начинается парсинг сайта: {self.name}")
        jobs = []
        url = self.start_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for _ in range(PAGES_LIMIT):
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("div.card.card-hover.card-visited.wordwrap.job-link", timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning("Путь к вакансиям на странице не найден или страница не загрузилась.")
                    break

                vacancies = await page.query_selector_all("div.card.card-hover.card-visited.wordwrap.job-link")

                for v in vacancies:
                    title_link = await v.query_selector("h2.my-0 a")
                    if not title_link:
                        continue

                    href = await title_link.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = "https://www.work.ua" + href

                    title = (await title_link.inner_text()).strip()

                    date_el = await v.query_selector("div.flex.flex-align-center.flex-wrap time")
                    date = ""
                    if date_el:
                        datetime_attr = await date_el.get_attribute("datetime")
                        if datetime_attr:
                            dt = datetime.strptime(datetime_attr, "%Y-%m-%d %H:%M:%S")
                            date = dt.strftime("%d.%m.%Y %H:%M")

                    job_page = await browser.new_page()
                    await job_page.goto(href, wait_until="domcontentloaded")
                    try:
                        await job_page.wait_for_selector("div#job-description", timeout=5000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Описание вакансии не найдено: {href}")
                        pass
                    desc_el = await job_page.query_selector("div#job-description")
                    desc = (await desc_el.inner_text()).strip() if desc_el else ""
                    await job_page.close()

                    jobs.append({
                        "title": title,
                        "link": href,
                        "description": desc,
                        "source": self.name,
                        "date": date if date else ""
                    })

                    if len(jobs) >= DETAILS_LIMIT:
                        logger.info(f"Достигнут лимит вакансий, прекращаем сбор.")
                        break

                if len(jobs) >= DETAILS_LIMIT:
                    break

                next_btn = await page.query_selector("a[aria-label='Наступна сторінка']")
                if next_btn:
                    next_href = await next_btn.get_attribute("href")
                    if next_href:
                        url = "https://www.work.ua" + next_href
                    else:
                        break
                else:
                    break

            await browser.close()
            logger.info(f"Парсинг сайта завершен.")

        return jobs

class RobotaUA:
    name = "robota.ua"
    start_url = "https://robota.ua/zapros/ukraine/params;scheduleIds=3;rubrics=1-404,1-429,1-439;salaryType=false"

    async def run(self) -> List[Dict]:
        logger.info(f"Начинается парсинг сайта: {self.name}")
        jobs = []
        url = self.start_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for _ in range(PAGES_LIMIT):
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("a.card[href*='/vacancy']", timeout=60000)
                except PlaywrightTimeoutError:
                    logger.warning(f"Путь к вакансиям на странице не найден или страница не загрузилась.")
                    break
                vacancies = await page.query_selector_all("a.card[href*='/vacancy']")

                for v in vacancies:
                    title_link = await v.query_selector("h2")
                    if not title_link:
                        continue

                    href = await v.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = "https://robota.ua" + href
                    title = (await title_link.inner_text()).strip() if title_link else ""

                    job_page = await browser.new_page()
                    await job_page.goto(href, wait_until="domcontentloaded")
                    try:
                        await job_page.wait_for_selector("div.full-desc", timeout=8000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Описание вакансии не найдено: {href}")
                        pass
                    desc_el = await job_page.query_selector("div.full-desc")
                    desc = (await desc_el.inner_text()).strip() if desc_el else ""

                    date_el = await job_page.wait_for_selector("span.santa-typo-regular.santa-whitespace-nowrap", timeout=5000)
                    raw_date = (await date_el.inner_text()).strip() if date_el else ""

                    date = ""
                    if raw_date:
                        parts = raw_date.split()
                        if len(parts) >= 2:
                            num_str, unit = parts[0], parts[1]
                            try:
                                num = int(num_str)
                            except ValueError:
                                num = 1

                            now = datetime.now()

                            if "день" in unit or "дн" in unit:
                                date_obj = now - timedelta(days=num)
                            elif "годин" in unit or "год" in unit:
                                date_obj = now - timedelta(hours=num)
                            elif "тиждень" in unit or "тижд" in unit:
                                date_obj = now - timedelta(weeks=num)
                            elif "місяць" in unit:
                                date_obj = now - timedelta(days=30 * num)
                            elif "рік" in unit:
                                date_obj = now - timedelta(days=365 * num)
                            else:
                                date_obj = now

                            date = date_obj.strftime("%d.%m.%Y %H:%M")
                    await job_page.close()

                    jobs.append({
                        "title": title,
                        "link": href,
                        "description": desc,
                        "source": self.name,
                        "date": date if date else ""
                    })

                    if len(jobs) >= DETAILS_LIMIT:
                        logger.info(f"Достигнут лимит вакансий, прекращаем сбор.")
                        break

                if len(jobs) >= DETAILS_LIMIT:
                    break

                next_btn = await page.query_selector("a[aria-label='Наступна сторінка']")
                if next_btn:
                    next_href = await next_btn.get_attribute("href")
                    if next_href:
                        url = "https://robota.ua" + next_href
                    else:
                        break
                else:
                    break

            await browser.close()
            logger.info(f"Парсинг сайта завершен.")

        return jobs

class OlxUA:
    name = "olx.ua"
    start_url = "https://www.olx.ua/uk/rabota/it-telekom-kompyutery/drugoe/?currency=UAH&search%5Bfilter_enum_job_type%5D%5B0%5D=remote&search%5Bfilter_enum_job_type%5D%5B1%5D=perm&search%5Bfilter_enum_job_type%5D%5B2%5D=part_time&search%5Border%5D=created_at%3Adesc"

    async def run(self) -> List[Dict]:
        logger.info(f"Начинается парсинг сайта: {self.name}")
        jobs = []
        url = self.start_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for _ in range(PAGES_LIMIT):
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("div.jobs-ad-card", timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning("Путь к вакансиям на странице не найден или страница не загрузилась.")
                    break

                vacancies = await page.query_selector_all("div.jobs-ad-card")

                for v in vacancies:
                    title_link = await v.query_selector("div.css-1s4cikj a")
                    if not title_link:
                        continue

                    href = await title_link.get_attribute("href")
                    if not href:
                        continue

                    if href.startswith("/"):
                        href = "https://www.olx.ua" + href

                    title = (await title_link.inner_text()).strip() if title_link else ""

                    date_el = await v.query_selector("p.css-996jis")
                    raw_date = (await date_el.inner_text()).strip() if date_el else ""

                    ukr_months = {
                        "січня": "01", "лютого": "02", "березня": "03", "квітня": "04",
                        "травня": "05", "червня": "06", "липня": "07", "серпня": "08",
                        "вересня": "09", "жовтня": "10", "листопада": "11", "грудня": "12"
                    }

                    date = ""
                    now = datetime.now()

                    if raw_date:
                        raw_lower = raw_date.lower()
                        if "сьогодні" in raw_lower:
                            time_part = raw_date.split("о")[-1].strip() if "о" in raw_date else "00:00"
                            try:
                                t = datetime.strptime(time_part, "%H:%M").time()
                            except ValueError:
                                t = datetime.min.time()
                            date = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).strftime(
                                "%d.%m.%Y %H:%M")
                        elif "вчора" in raw_lower:
                            time_part = raw_date.split("о")[-1].strip() if "о" in raw_date else "00:00"
                            try:
                                t = datetime.strptime(time_part, "%H:%M").time()
                            except ValueError:
                                t = datetime.min.time()
                            yesterday = now - timedelta(days=1)
                            date = yesterday.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).strftime(
                                "%d.%m.%Y %H:%M")
                        else:
                            parts = raw_date.split()
                            if len(parts) >= 3:
                                day = parts[0]
                                month_ua = parts[1].lower()
                                year = parts[2].replace("р.", "")
                                month = ukr_months.get(month_ua, "01")
                                date = f"{int(day):02d}.{month}.{year}"
                            else:
                                date = raw_date

                    job_page = await browser.new_page()
                    await job_page.goto(href, wait_until="domcontentloaded")
                    try:
                        desc_el = await job_page.wait_for_selector("div.css-1i3492", timeout=8000)
                        desc = (await desc_el.inner_text()).strip()
                    except PlaywrightTimeoutError:
                        logger.warning(f"Описание вакансии не найдено: {href}")
                        desc = ""
                    await job_page.close()

                    jobs.append({
                        "title": title,
                        "link": href,
                        "description": desc,
                        "source": self.name,
                        "date": date if date else ""
                    })

                    if len(jobs) >= DETAILS_LIMIT:
                        logger.info(f"Достигнут лимит вакансий, прекращаем сбор.")
                        break
                if len(jobs) >= DETAILS_LIMIT:
                    break
                next_btn = await page.query_selector("a[aria-label='Наступна сторінка']")
                if next_btn:
                    next_href = await next_btn.get_attribute("href")
                    if next_href:
                        url = "https://www.olx.ua" + next_href
                    else:
                        break
                else:
                    break
            await browser.close()
            logger.info(f"Парсинг сайта завершен.")
        return jobs

class DouUA:
    name = "dou.ua"
    start_url = "https://jobs.dou.ua/vacancies/?category=Python&exp=1-3"

    async def run(self) -> List[Dict]:
        logger.info(f"Начинается парсинг сайта: {self.name}")
        jobs = []
        url = self.start_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for _ in range(PAGES_LIMIT):
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("li.l-vacancy", timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning("Путь к вакансиям на странице не найден или страница не загрузилась.")
                    break

                vacancies = await page.query_selector_all("li.l-vacancy")

                for v in vacancies:
                    title_link = await v.query_selector("div.title a.vt")
                    if not title_link:
                        continue

                    href = await title_link.get_attribute("href")
                    title = (await title_link.inner_text()).strip() if title_link else ""

                    date_el = await v.query_selector("div.date")
                    raw_date = (await date_el.inner_text()).strip() if date_el else ""

                    ukr_months = {
                        "січня": "01", "лютого": "02", "березня": "03", "квітня": "04",
                        "травня": "05", "червня": "06", "липня": "07", "серпня": "08",
                        "вересня": "09", "жовтня": "10", "листопада": "11", "грудня": "12"
                    }

                    if raw_date:
                        parts = raw_date.split()
                        if len(parts) == 2:
                            day, month_ua = parts
                            month = ukr_months.get(month_ua.lower(), "01")
                            year = datetime.now().year
                            date = f"{int(day):02d}.{month}.{year}"
                        else:
                            date = raw_date
                    else:
                        date = ""

                    job_page = await browser.new_page()
                    await job_page.goto(href, wait_until="domcontentloaded")
                    try:
                        await job_page.wait_for_selector("div.b-typo.vacancy-section", timeout=8000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Описание вакансии не найдено: {href}")
                        pass
                    desc_el = await job_page.query_selector("div.b-typo.vacancy-section")
                    desc = (await desc_el.inner_text()).strip() if desc_el else ""
                    await job_page.close()

                    jobs.append({
                        "title": title,
                        "link": href,
                        "description": desc,
                        "source": self.name,
                        "date": date if date else ""
                    })

                    if len(jobs) >= DETAILS_LIMIT:
                        logger.info(f"Достигнут лимит вакансий, прекращаем сбор.")
                        break

                if len(jobs) >= DETAILS_LIMIT:
                    break

                next_btn = await page.query_selector("a[aria-label='Наступна сторінка']")
                if next_btn:
                    next_href = await next_btn.get_attribute("href")
                    if next_href:
                        url = "https://jobs.dou.ua" + next_href
                    else:
                        break
                else:
                    break

            await browser.close()
            logger.info(f"Парсинг сайта завершен.")

        return jobs

class Djinni:
    name = "djinni.co"
    start_url = "https://djinni.co/jobs/?primary_keyword=Python&exp_level=1y&exp_level=2y&employment=remote"

    async def run(self) -> List[Dict]:
        logger.info(f"Начинается парсинг сайта: {self.name}")
        jobs = []
        url = self.start_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for _ in range(PAGES_LIMIT):
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("ul.list-unstyled.list-jobs.mb-4 li", timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning("Путь к вакансиям на странице не найден или страница не загрузилась.")
                    break

                vacancies = await page.query_selector_all("ul.list-unstyled.list-jobs.mb-4 li")

                for v in vacancies:
                    title_link = await v.query_selector("h2.fs-3.mb-2 a.job-item__title-link")
                    if not title_link:
                        continue

                    href = await title_link.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = "https://djinni.co" + href

                    title = (await title_link.inner_text()).strip()

                    date_el = await v.query_selector("span.text-nowrap[data-original-title]")
                    date_attr = await date_el.get_attribute("data-original-title")
                    date = date_attr.split()[1] if date_attr else ""

                    job_page = await browser.new_page()
                    await job_page.goto(href, wait_until="domcontentloaded")
                    try:
                        await job_page.wait_for_selector("div.mb-4.job-post__description", timeout=8000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Описание вакансии не найдено: {href}")
                        pass
                    desc_el = await job_page.query_selector("div.mb-4.job-post__description")
                    desc = (await desc_el.inner_text()).strip() if desc_el else ""
                    await job_page.close()

                    jobs.append({
                        "title": title,
                        "link": href,
                        "description": desc,
                        "source": self.name,
                        "date": date if date else ""
                    })

                    if len(jobs) >= DETAILS_LIMIT:
                        logger.info(f"Достигнут лимит вакансий, прекращаем сбор.")
                        break

                if len(jobs) >= DETAILS_LIMIT:
                    break

                next_btn = await page.query_selector("a[aria-label='Наступна сторінка']")
                if next_btn:
                    next_href = await next_btn.get_attribute("href")
                    if next_href:
                        url = "https://djinni.co/jobs" + next_href
                    else:
                        break
                else:
                    break

            await browser.close()
            logger.info(f"Парсинг сайта завершен.")

        return jobs

# ================= ОТПРАВКА =================
async def send_job(job: Dict):
    text = (
        f"<b>{job['title']}</b>\n\n"
        f"{job['description'][:2000]}\n\n"
        f"Дата публикации вакансии: {job['date']}\n"
        f"Источник: <i>{job['source']}</i>\n"
        f"<a href=\"{job['link']}\">Ссылка</a>"
    )
    subs = await get_subscribers()
    for uid in subs:
        try:
            await bot.send_message(uid, text, disable_web_page_preview=True)
        except exceptions.TelegramAPIError as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")

# ================= ЦИКЛ =================
PARSERS: List[Type] = [
    WorkUA,
    RobotaUA,
    OlxUA,
    DouUA,
    Djinni
]

async def scrape_loop():
    await init_db()
    while True:
        logger.info("Начало нового цикла поиска вакансий...")
        for parser_cls in PARSERS:
            parser = parser_cls()
            try:
                jobs = await parser.run()
            except Exception as e:
                logger.error(f"Ошибка при работе {parser.name}: {e}")
                continue
            new_jobs_count = 0

            for job in jobs:
                if not await job_seen(job["source"], job["description"], job["title"]):
                    await send_job(job)
                    new_jobs_count += 1
                    await asyncio.sleep(0.5)

            logger.info(f"Всего вакансий: {len(jobs)}, новых отправлено: {new_jobs_count}")

        await asyncio.sleep(FETCH_INTERVAL)

# ================= КОМАНДЫ БОТА =================
@router.message(Command("start", "help"))
async def cmd_start(message: Message):
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO subscribers (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    await message.answer("Привет! Я присылаю новые IT-вакансии.\n"
                         "Команды: /stop — отписка, /status — статус.")

@router.message(Command("stop"))
async def cmd_stop(message: Message):
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscribers WHERE user_id = ?", (message.from_user.id,))
        await db.commit()
    await message.answer("Вы отписались.")

@router.message(Command("status"))
async def cmd_status(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM seen_jobs")
        seen_count = (await cur.fetchone())[0]
    await message.answer(f"Вакансий в базе: {seen_count}\n"
                         f"Интервал: {FETCH_INTERVAL // 60} мин.")

# ================= MAIN =================
async def main():
    await init_db()
    asyncio.create_task(scrape_loop())
    await dp.start_polling(bot, allowed_updates=["message"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка...")
