import json
import os
from datetime import datetime, timedelta
import aiofiles
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import asyncio
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
import logging
from aiogram import loggers as aiogram_loggers

TOKEN = "BotToken"
bot = Bot(token=TOKEN)
dp = Dispatcher()

json_folder = 'data'
os.makedirs(json_folder, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("sinoptik-bot")
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
            "Polling stopped for bot": "Получение обновлений остановлено для бота",
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
        "sinoptik-bot",
    ):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

def time(dt_utc):
    local_dt = dt_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Kyiv"))
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


class Form(StatesGroup):
    waiting_for_city = State()
    waiting_for_new_city = State()
    waiting_for_city_confirmation = State()
    waiting_for_weather_choice = State()

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}
    else:
        user_data = {}

    user_id = str(message.from_user.id)
    if user_id in user_data:
        city = user_data[user_id]
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
            ],
            resize_keyboard=True
        )
        await message.answer(f"Давно не виделись ₍^ >ヮ<^₎ !\nКотик всё ещё живёт в {city.capitalize()}?", reply_markup=kb)
        await state.set_state(Form.waiting_for_city_confirmation)
    else:
        await message.answer("₍^. .^₎⟆ Мяу?\nГде живёт котик?\n\n(укажите Ваш город)")
        await state.set_state(Form.waiting_for_city)

@dp.message(Form.waiting_for_city_confirmation)
async def city_confirmation(message: Message, state: FSMContext):
    if message.text == "Да":
        await message.answer("Чудесно! Хотите узнать погоду? ฅ≽(•⩊ •マ≼\nНапишите /cat_sinoptik", reply_markup=ReplyKeyboardRemove())
        await state.clear()
    elif message.text == "Нет":
        await message.answer("Укажите новый город:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.waiting_for_city)
    else:
        await message.answer("Пожалуйста, выберите: Да или Нет.")

@dp.message(Form.waiting_for_city)
async def get_city(message: Message, state: FSMContext):
    logger.info(f"{message.from_user.full_name} живёт в: {message.text.capitalize()}")
    await message.answer("Хотите узнать что говорят уличные котики? - ˕ •マ\nОтправьте команду /cat_sinoptik")
    await state.clear()

    user_file_path = f'{json_folder}/user_data.json'
    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}

    user_data[str(message.from_user.id)] = message.text.capitalize()
    async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
        json_data = json.dumps(user_data, ensure_ascii=False, indent=4)
        await f.write(json_data)
    async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        return json.loads(content)


@dp.message(Command("change_city"))
async def cmd_change_city(message: Message, state: FSMContext):
    await message.answer("Введите новый город:")
    await state.set_state(Form.waiting_for_new_city)

@dp.message(Form.waiting_for_new_city)
async def new_city(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}

    user_data[str(message.from_user.id)] = message.text.capitalize()
    async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
        json_data = json.dumps(user_data, ensure_ascii=False, indent=4)
        await f.write(json_data)
    await message.answer(f"Город успешно изменён на {message.text.capitalize()}!")
    logger.info(f"Город пользователя {message.from_user.full_name} обновлён на: {message.text.capitalize()}")
    await state.clear()


def normalize_city(city):
    exceptions = {'киев': 'kyiv','днепр': 'dnipro','одесса': 'odesa','львов': 'lviv','харьков': 'kharkiv','запорожье': 'zaporizhzhia','черновцы': 'chernivtsi',
        'ивано-франковск': 'ivano-frankivsk','ужгород': 'uzhhorod','кропивницкий': 'kropyvnytskyi','луцк': 'lutsk','винница': 'vinnytsia','черкассы': 'cherkasy',
        'тернополь': 'ternopil','житомир': 'zhytomyr', 'чернигов': 'chernihiv','полтава': 'poltava','сумы': 'sumy','мариуполь': 'mariupol','белая церковь': 'bila-tserkva',
        'каменец-подольский': 'kamianets-podilskyi','николаев': 'mykolaiv','херсон': 'kherson','мелитополь': 'melitopol','кременчуг': 'kremenchuk','бердянск': 'berdyansk',
        'покровск': 'pokrovsk','словакия': 'sloviansk', 'дружковка': 'druzhkivka'
    }
    city_lower = city.strip().lower()
    if city_lower in exceptions:
        return exceptions[city_lower]
    translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
        'з': 'z', 'и': 'y', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ы': 'y', 'э': 'e', 'ю': 'iu', 'я': 'ia',
        'ь': '', 'ъ': '', 'і': 'i', 'ї': 'i', 'є': 'ie'
    }
    return ''.join([translit.get(c, c) if c != ' ' else '-' for c in city_lower])


async def weather(user_id, days_count=1):
    user_file_path = f'{json_folder}/user_data.json'
    city_file_path = f'{json_folder}/city_data.json'
    async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        user_data = json.loads(content)
        city = user_data.get(str(user_id))
    if not city:
        return "Вы ещё не сказали, где живёте! Напишите свой город, чтобы узнать погоду 🐾"
    city_url = normalize_city(city)
    days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
    now = datetime.now()

    try:
        async with aiofiles.open(city_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            if content.strip():
                city_data = json.loads(content)
            else:
                city_data = {}
    except FileNotFoundError:
        city_data = {}

    if city not in city_data:
        city_data[city] = {}

    result = ""
    dates_needed_from_site = []

    needed_dates = []
    for offset in range(days_count):
        current_day = now + timedelta(days=offset)
        weekday = days[current_day.weekday()].capitalize()
        day_str = str(int(current_day.strftime('%d')))
        date_key = f"{weekday} {day_str}"
        needed_dates.append(date_key)

        if date_key in city_data[city]:
            min_temp = city_data[city][date_key]["min"]
            max_temp = city_data[city][date_key]["max"]
            result += f"{date_key}\n🌡 Минимальная (ночь): {min_temp}\n🌡 Максимальная (день): {max_temp}\n\n"
        else:
            dates_needed_from_site.append(date_key)

    if not dates_needed_from_site:
        return f"ദ്ദി/ᐠ - ⩊ -マ\n\n{result.strip()}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

        try:
            await page.goto(f"https://sinoptik.ua/ru/pohoda/{city_url}/10-dniv", timeout=90000)
            await asyncio.sleep(3)
        except Exception as e:
            await browser.close()
            logger.error(f"Не удалось загрузить страницу: {str(e)}")
            return "Котикам было лень изучать погоду!"

        for date in dates_needed_from_site:
            if date in city_data[city]:
                min_temp = city_data[city][date]["min"]
                max_temp = city_data[city][date]["max"]
            else:
                try:
                    day_link = await page.get_by_role("link", name=date).nth(0).inner_text()
                    day_text = day_link.split('\n')
                    min_temp = day_text[8] if len(day_text) > 8 else "нет данных"
                    max_temp = day_text[12] if len(day_text) > 12 else "нет данных"
                except Exception as e:
                    logger.error(f"Ошибка получения данных для {date}: {e}")
                    return "Котики не понимают работу термометра..?"

                city_data[city][date] = {"min": min_temp, "max": max_temp}

            result += f"{date}\n🌡 Минимальная (ночь): {min_temp}\n🌡 Максимальная (день): {max_temp}\n\n"

        await browser.close()

        async with aiofiles.open(city_file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(city_data, indent=2, ensure_ascii=False))

        logger.info("Погода получена и сохранена в json")
        return f"ദ്ദി/ᐠ - ⩊ -マ\n\n{result.strip()}"

@dp.message(Command("cat_sinoptik"))
async def cmd_weather(message: Message, state: FSMContext):
    weather_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Погода на день")],
            [KeyboardButton(text="Погода на неделю")],
            [KeyboardButton(text="Погода на 10 дней")]
        ],
        resize_keyboard=True
    )
    await message.answer("Как много информации получить от уличных котиков?", reply_markup=weather_kb)
    await state.set_state(Form.waiting_for_weather_choice)

@dp.message(Form.waiting_for_weather_choice)
async def weather_choice(message: Message, state: FSMContext):
    choice = message.text
    await state.clear()
    wait = await message.answer ("Слушаю шёпот котиков...\n/ᐠ - ˕ -マ Ⳋ", reply_markup=ReplyKeyboardRemove())
    try:
        if choice == "Погода на день":
            info = await weather(message.from_user.id, days_count=1)
        elif choice == "Погода на неделю":
            info = await weather(message.from_user.id, days_count=7)
        elif choice == "Погода на 10 дней":
            info = await weather(message.from_user.id, days_count=10)
        else:
            info = "Котики не знают такой команды..."
        await wait.delete()
        await message.answer(info)
    except Exception as e:
        await message.answer("Уличные котики пока спят")
        logger.error(f"Ошибка при получении погоды: {str(e)}")


@dp.message()
async def echo_message(message: types.Message):
    logger.info(f"Получено сообщение от {message.from_user.full_name}: {message.text}")
    await message.answer("/ᐠ • ˕ •マ ?")


async def main():
    await bot.get_updates(offset=-1)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())