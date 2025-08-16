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
            print (f"Не удалось загрузить страницу: {str(e)}")
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
                    print(f"Ошибка получения данных для {date}: {e}")
                    return "Котики не понимают работу термометра..?"

                city_data[city][date] = {"min": min_temp, "max": max_temp}

            result += f"{date}\n🌡 Минимальная (ночь): {min_temp}\n🌡 Максимальная (день): {max_temp}\n\n"

        await browser.close()

        async with aiofiles.open(city_file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(city_data, indent=2, ensure_ascii=False))

        print("Погода получена и сохранена в json")
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
        print(f"[{time(message.date)}] Ошибка при получении погоды: {str(e)}")

