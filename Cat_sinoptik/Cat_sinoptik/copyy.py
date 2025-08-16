import asyncio
import os
import random
from zoneinfo import ZoneInfo
import aiohttp

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, Message

TOKEN = "7628346670:AAFBAwD5IMx91YUfGixwGbdxOqCOeCEDWZ4"

bot = Bot(token=TOKEN)
dp = Dispatcher()

SAVE_DIR = "C:\\MyFiles\\Projects\\Pyton\\Moon_cats\\Moon_cats\\photos"
os.makedirs(SAVE_DIR, exist_ok=True)

def time(dt_utc):
    local_dt = dt_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Kyiv"))
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")

# Команды
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Мяу-мяу?")

@dp.message(Command("i_love_cats"))
async def cmd_love(message: Message):
    await message.answer("А я люблю Муна!♡")

# Картинка кота
async def download_image(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return True
    return False

@dp.message(Command("cat"))
async def cmd_cat(message: Message):
    random_number = random.randint(1, 100000)
    url = f"https://cataas.com/cat?random={random_number}"
    filename = os.path.join(SAVE_DIR, f"cat_{random_number}.jpg")
    success = await download_image(url, filename)
    if success:
        await message.answer_photo(photo=FSInputFile(filename), caption="Ня-ня!")
        print(f"[{time(message.date)}] Скачано и отправлено: {filename}")
    else:
        await message.answer("Не удалось загрузить котика...")

@dp.message()
async def echo_message(message: types.Message):
    print(f"[{time(message.date)}] Получено сообщение от {message.from_user.full_name}: {message.text}")
    await message.answer("/ᐠ • ˕ •マ ?")

#Запуск
async def main():
    await bot.get_updates(offset=-1)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
