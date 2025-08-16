import json
import logging
from aiogram import loggers as aiogram_loggers
import aiohttp
import os
import aiofiles
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import asyncio
from rapidfuzz import fuzz

TOKEN = "BotToken"
bot = Bot(token=TOKEN)
dp = Dispatcher()

json_folder = 'data'
os.makedirs(json_folder, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("library-bot")
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
        "library-bot",
    ):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

class Form(StatesGroup):
    waiting_for_library_confirmation = State()
    adding_list_choice = State()
    waiting_for_book_title = State()
    waiting_for_book_author = State()

    changing_list_choice = State()
    waiting_for_action_choice = State()
    waiting_for_book_number = State()

    waiting_for_info_choice = State()
    waiting_for_list_choice_info = State()
    waiting_for_book_number_info = State()
    waiting_for_new_book_title = State()
    waiting_for_new_book_author = State()

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
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]],
            resize_keyboard=True
        )
        await message.answer(f"Приветствую снова!\nХотите сохранить Вашу библиотеку?", reply_markup=kb)
        await state.set_state(Form.waiting_for_library_confirmation)
    else:
        user_data[user_id] = {"прочитанные книги": {}, "желанные книги": {}}
        async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
            json_data = json.dumps(user_data, ensure_ascii=False, indent=4)
            await f.write(json_data)
        await message.answer(
            "Здравствуй!\nДобро пожаловать в книжный уголок.\nВыберите команду в меню для начала работы.", reply_markup=ReplyKeyboardRemove())

@dp.message(Form.waiting_for_library_confirmation)
async def library_confirmation(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)

    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}

    if message.text == "Нет":
        if user_id in user_data:
            user_data[user_id]["прочитанные книги"] = {}
            user_data[user_id]["желанные книги"] = {}

            async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
                json_data = json.dumps(user_data, ensure_ascii=False, indent=4)
                await f.write(json_data)

            await message.answer("Ваша библиотека была очищена.\nВы можете начать с чистого листа!\nВыберите команду в меню для продолжения.", reply_markup=ReplyKeyboardRemove())
            logger.info(f"Библиотека пользователя {message.from_user.full_name} была очищена")
        else:
            await message.answer("Что-то пошло не так... Ваш профиль не найден.", reply_markup=ReplyKeyboardRemove())

    elif message.text == "Да":
        await message.answer("Отлично! Ваша библиотека сохранена.\nВыберите команду в меню для продолжения.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Библиотека пользователя {message.from_user.full_name} была сохранена")
    else:
        await message.answer("Пожалуйста, выберите: Да или Нет.")
        return

    await state.clear()


@dp.message(Command("wish_to_read"))
async def cmd_wish_to_read(message: Message):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)

    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}

        if user_id in user_data and user_data[user_id].get("желанные книги"):
            wish_list = user_data[user_id]["желанные книги"]
            if wish_list:
                book_list = "\n".join([f"{num}. {book}" for num, book in wish_list.items()])
                await message.answer(f"Список желанных книг:\n\n{book_list}")
                logger.info(f"Пользователю {message.from_user.full_name} отправлен список желанных книг")
            else:
                await message.answer("Список желанных книг пуст. Добавьте книги командой /add_book")
        else:
            await message.answer("Список желанных книг пуст. Добавьте книги командой /add_book")

@dp.message(Command("my_library"))
async def cmd_my_library(message: Message):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)

    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}

        if user_id in user_data and user_data[user_id].get("прочитанные книги"):
            read_list = user_data[user_id]["прочитанные книги"]
            if read_list:
                book_list = "\n".join([f"{num}. {book}" for num, book in read_list.items()])
                await message.answer(f"Список прочитанных книг:\n\n{book_list}")
                logger.info(f"Пользователю {message.from_user.full_name} отправлен список прочитанных книг")
            else:
                await message.answer("Список прочитанных книг пуст. Добавьте книги командой /add_book")
        else:
            await message.answer("Список прочитанных книг пуст. Добавьте книги командой /add_book")


@dp.message(Command("add_book"))
async def cmd_add_book(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Прочитанные книги"),KeyboardButton(text="Желанные книги")]],
        resize_keyboard=True
    )
    await message.answer("В какой список хотите добавить книгу?", reply_markup=kb)
    await state.set_state(Form.adding_list_choice)

@dp.message(Form.adding_list_choice)
async def process_list_choice(message: Message, state: FSMContext):
    if message.text not in ["Прочитанные книги", "Желанные книги"]:
        await message.answer("Пожалуйста, выберите список.")
        return
    await state.update_data(list_choice=message.text)
    await message.answer("Введите название книги:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_book_title)

@dp.message(Form.waiting_for_book_title)
async def process_book_title(message: Message, state: FSMContext):
    book_title = message.text.capitalize()
    await state.update_data(book_title=book_title)
    await message.answer("Теперь укажите автора книги (если не знаете, можете поставить -, но это ограничит доступ к информации о книге):")
    await state.set_state(Form.waiting_for_book_author)

@dp.message(Form.waiting_for_book_author)
async def process_book(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)

    user_data_fsm = await state.get_data()
    list_choice = user_data_fsm.get("list_choice")
    book_title = user_data_fsm.get("book_title")
    book_author = message.text.title()
    book_full = f"{book_title} - {book_author}"

    if os.path.exists(user_file_path):
        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                user_data = json.loads(content)
            except json.JSONDecodeError:
                user_data = {}
    else:
        user_data = {}

    if user_id not in user_data:
        user_data[user_id] = {"прочитанные книги": {}, "желанные книги": {}}

    if list_choice == "Прочитанные книги":
        target_list = user_data[user_id]["прочитанные книги"]
    else:
        target_list = user_data[user_id]["желанные книги"]

    new_num = str(len(target_list) + 1)
    target_list[new_num] = book_full

    if list_choice == "Прочитанные книги":
        user_data[user_id]["прочитанные книги"] = target_list
    else:
        user_data[user_id]["желанные книги"] = target_list

    async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
        json_data = json.dumps(user_data, ensure_ascii=False, indent=4)
        await f.write(json_data)

    await message.answer(f"Спасибо! Книга «{book_full}» успешно добавлена в список {list_choice}.", reply_markup=ReplyKeyboardRemove())
    logger.info(f"Пользователь {message.from_user.full_name} добавил «{book_full}» в список {list_choice}")
    await state.clear()


@dp.message(Command("change_books"))
async def cmd_change_books(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Прочитанные книги"), KeyboardButton(text="Желанные книги")]],
        resize_keyboard=True
    )
    await message.answer("Выберите список для изменения:", reply_markup=kb)
    await state.set_state(Form.changing_list_choice)

@dp.message(Form.changing_list_choice)
async def process_list_choice_change(message: Message, state: FSMContext):
    if message.text not in ["Прочитанные книги", "Желанные книги"]:
        await message.answer("Выберите список, который хотите изменить.")
        return
    await state.update_data(list_choice=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Добавить книгу"), KeyboardButton(text="Удалить книгу")]],
        resize_keyboard=True
    )
    await message.answer("Что вы хотите сделать?", reply_markup=kb)
    await state.set_state(Form.waiting_for_action_choice)

@dp.message(Form.waiting_for_action_choice)
async def process_action_choice(message: Message, state: FSMContext):
    user_data = await state.get_data()
    list_choice = user_data.get("list_choice")

    if message.text == "Добавить книгу":
        await message.answer("Введите название книги:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.waiting_for_book_title)
        return
    elif message.text == "Удалить книгу":
        user_file_path = f'{json_folder}/user_data.json'
        user_id = str(message.from_user.id)

        async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
            try:
                all_data = json.loads(await f.read())
            except json.JSONDecodeError:
                all_data = {}

        if user_id not in all_data:
            await message.answer("Нет сохранённых данных. Используйте /add_book для добавления.")
            await state.clear()
            return

        target_list = all_data[user_id]["прочитанные книги"] if list_choice == "Прочитанные книги" else \
        all_data[user_id]["желанные книги"]

        if not target_list:
            await message.answer("Список пуст. Добавьте книги через /add_book.")
            await state.clear()
            return

        books = "\n".join([f"{num}. {book}" for num, book in target_list.items()])
        await message.answer(f"Список:\n\n{books}\n\nУкажите номер книги (цифрой) или несколько номеров (через запятую) для удаления")
        await state.set_state(Form.waiting_for_book_number)
    else:
        await message.answer("Пожалуйста, выберите действие: Добавить книгу или Удалить книгу.")

@dp.message(Form.waiting_for_book_number)
async def process_book_number(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)
    data = await state.get_data()
    list_choice = data.get("list_choice")
    nums = message.text.replace(' ', '').split(',')
    num_to_delete = [num for num in nums if num.isdigit()]
    if not num_to_delete:
        await message.answer("Пожалуйста, введите номер книги (цифрой) или несколько номеров (через запятую).")
        return

    async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
        try:
            all_data = json.loads(await f.read())
        except json.JSONDecodeError:
            all_data = {}

    target_list = all_data[user_id]["прочитанные книги"] if list_choice == "Прочитанные книги" else all_data[user_id]["желанные книги"]

    invalid_nums = [num for num in num_to_delete if num not in target_list]
    if invalid_nums:
        await message.answer(f"Неверный номер: {', '.join(invalid_nums)}. Проверьте список и попробуйте снова.")
        return

    deleted_book = [target_list.pop(num) for num in num_to_delete]
    new_list = {str(i + 1): v for i, v in enumerate(target_list.values())}

    if list_choice == "Прочитанные книги":
        all_data[user_id]["прочитанные книги"] = new_list
    else:
        all_data[user_id]["желанные книги"] = new_list

    async with aiofiles.open(user_file_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(all_data, ensure_ascii=False, indent=4))

    deleted_text = ", ".join([f"<<{book}>>" for book in deleted_book])
    await message.answer(f"Книга «{deleted_text}» удалена из списка {list_choice}.", reply_markup=ReplyKeyboardRemove())
    logger.info(f"Пользователь {message.from_user.full_name} удалил  «{', '.join(deleted_book)}» из списка {list_choice}")
    await state.clear()


@dp.message(Command("book_info"))
async def cmd_book_info(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Выбрать из списка"), KeyboardButton(text="Указать новую книгу")]],
        resize_keyboard=True
    )
    await message.answer("Хотите выбрать книгу из списка или указать новую?", reply_markup=kb)
    await state.set_state(Form.waiting_for_info_choice)

@dp.message(Form.waiting_for_info_choice)
async def process_info_choice(message: Message, state: FSMContext):
    if message.text == "Выбрать из списка":
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Прочитанные книги"), KeyboardButton(text="Желанные книги")]],
            resize_keyboard=True
        )
        await message.answer("Из какого списка выбрать книгу?", reply_markup=kb)
        await state.set_state(Form.waiting_for_list_choice_info)
    elif message.text == "Указать новую книгу":
        await message.answer("Введите название книги:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.waiting_for_new_book_title)
    else:
        await message.answer("Пожалуйста, выберите один из вариантов.")

@dp.message(Form.waiting_for_list_choice_info)
async def process_list_choice_info(message: Message, state: FSMContext):
    if message.text not in ["Прочитанные книги", "Желанные книги"]:
        await message.answer("Пожалуйста, выберите корректный список.")
        return
    await state.update_data(list_choice=message.text)
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)

    async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        all_data = json.loads(content) if content else {}

    target_list = all_data.get(user_id, {}).get(
        "прочитанные книги" if message.text == "Прочитанные книги" else "желанные книги", {})

    if not target_list:
        await message.answer("Список пуст.")
        await state.clear()
        return

    books = "\n".join([f"{num}. {book}" for num, book in target_list.items()])
    await message.answer(f"Список:\n\n{books}\n\nВведите номер книги:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_book_number_info)

@dp.message(Form.waiting_for_book_number_info)
async def process_book_number_info(message: Message, state: FSMContext):
    user_file_path = f'{json_folder}/user_data.json'
    user_id = str(message.from_user.id)
    data = await state.get_data()
    list_choice = data.get("list_choice")
    num = message.text.strip()
    if not num.isdigit():
        await message.answer("Пожалуйста, введите номер книги (цифрой) или несколько номеров (через запятую).")
        return

    async with aiofiles.open(user_file_path, 'r', encoding='utf-8') as f:
        try:
            all_data = json.loads(await f.read())
        except json.JSONDecodeError:
            all_data = {}

    target_list = all_data[user_id]["прочитанные книги"] if list_choice == "Прочитанные книги" else all_data[user_id]["желанные книги"]
    book = target_list.get(num)
    if not book:
        await message.answer(f"Неверный номер. Проверьте список и попробуйте снова.")
        return
    book_title, book_author = map(str.strip, book.split(" - ", 1))
    await state.update_data(book_info=book, book_title=book_title, book_author=book_author)
    logger.info(f"Пользователь {message.from_user.full_name} указал  «{book}» для поиска")
    await info_book(message, state)
    await state.clear()

@dp.message(Form.waiting_for_new_book_title)
async def process_new_book_title(message: Message, state: FSMContext):
    await state.update_data(book_title=message.text.title())
    await message.answer("Введите автора книги:")
    await state.set_state(Form.waiting_for_new_book_author)

@dp.message(Form.waiting_for_new_book_author)
async def process_new_book_author(message: Message, state: FSMContext):
    data = await state.get_data()
    book_title = data.get("book_title")
    book_author = message.text.title()
    book = f"{book_title} - {book_author}"
    await state.update_data(book_info=book, book_author=book_author)
    logger.info(f"Пользователь {message.from_user.full_name} указал  «{book}» для поиска")
    await info_book(message, state)
    await state.clear()

async def info_book(message: Message, state: FSMContext):
    book_path = f"{json_folder}/book.json"
    data = await state.get_data()
    user_input_title = data.get("book_title")
    user_input_author = data.get("book_author")
    if not user_input_title or not user_input_author:
        logger.warning("Ошибка: нет данных о названии или авторе книги.")
        return
    wait = await message.answer(f"Ведётся поиск книги «{user_input_title} - {user_input_author}»")

    try:
        async with aiofiles.open(book_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            book_cache = json.loads(content) if content.strip() else {}
    except FileNotFoundError:
        book_cache = {}

    input_title_lower = user_input_title.lower().strip()
    input_author_lower = user_input_author.lower().strip()

    found_key = None

    for author_name, books in book_cache.items():
        for book_title, info in books.items():
            cached_title = info.get('title', '').lower().strip()
            cached_authors = [a.lower().strip() for a in info.get('authors', [])]

            if cached_title == input_title_lower:
                input_author_parts = set(input_author_lower.split())
                for author in cached_authors:
                    author_parts = set(author.split())
                    if input_author_parts & author_parts:
                        found_key = (author_name, book_title)
                        break

            if found_key:
                break
        if found_key:
            break

    if found_key:
        author_name, book_title = found_key
        book_info = book_cache[author_name][book_title]
        await wait.delete()
        await message.answer(
            f"Название: {book_info['title']}\n"
            f"Авторы: {', '.join(book_info['authors'])}\n"
            f"Количество страниц: {book_info['pageCount']}\n"
            f"Описание: {book_info['description']}"
        )
        logger.info(f"Пользователю {message.from_user.full_name} дана информация про книгу из JSON")
        return

    query = f"intitle:{user_input_title} inauthor:{user_input_author}"
    base_url = "https://www.googleapis.com/books/v1/volumes"
    params = {'q': query, 'maxResults': 10}

    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, params=params) as resp:
            if resp.status != 200:
                logger.error(f"Ошибка запроса: {resp.status}")
                return

            data = await resp.json()
            full_result = None
            for item in data.get('items', []):
                volume_info = item['volumeInfo']
                api_title = volume_info.get('title', "")
                api_authors = volume_info.get('authors', [])
                if fuzz.ratio(user_input_title.lower(), api_title.lower()) >= 85:
                    pageCount = volume_info.get('pageCount', 0)
                    description = volume_info.get('description', '')
                    if pageCount == 0 and not description:
                        continue
                    main_author = api_authors[0] if api_authors else user_input_author
                    for existing_author in book_cache.keys():
                        if fuzz.partial_ratio(main_author.lower(), existing_author.lower()) >= 80:
                            main_author = existing_author
                            break

                    if full_result is None:
                        full_pages = pageCount > 0
                        full_description = len(description)>5
                        if full_pages and full_description:
                            full_result = {
                                "title": api_title,
                                "authors": api_authors,
                                "pageCount": pageCount if pageCount > 0 else 0,
                                "description": description if len(description)>5 else '',
                                "main_author": main_author,
                            }
                        elif not full_pages:
                            full_result = {
                                "title": api_title,
                                "authors": api_authors,
                                "pageCount": 0,
                                "description": description if len(description) > 5 else '',
                                "main_author": main_author,
                            }
                        elif not full_description:
                            full_result = {
                                "title": api_title,
                                "authors": api_authors,
                                "pageCount": pageCount if pageCount > 0 else 0,
                                "description": '',
                                "main_author": main_author,
                            }
                        continue
                    else:
                        if full_result ["pageCount"] == 0 and pageCount > 0:
                            full_result ["pageCount"] = pageCount
                        if len(full_result ["description"].strip()) < 1 and len(description.strip()) > 0:
                            full_result["description"] = description.strip()
                        if full_result ["pageCount"] > 0 and len(full_result["description"].strip())>0:
                            break

            if full_result:
                main_author = full_result["main_author"]
                api_title = full_result["title"]
                api_authors = full_result["authors"]
                pageCount = full_result["pageCount"]
                description = full_result["description"]

                if main_author not in book_cache:
                    book_cache[main_author] = {}
                book_cache[main_author][api_title] = {
                    "title": api_title,
                    "authors": api_authors,
                    "pageCount": pageCount,
                    "description": description
                }

                async with aiofiles.open(book_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(book_cache, ensure_ascii=False, indent=2))

                await wait.delete()
                await message.answer(f"Название: {api_title}\nАвтор: {main_author}\nКоличество страниц: {pageCount}\nОписание: {description}")
                logger.info(f"Пользователю {message.from_user.full_name} дана информация про книгу из поиска")
                return

            await message.answer("Книга не найдена или не удалось точно сопоставить по названию/автору с полными данными.")
            logger.warning(f"Пользователю {message.from_user.full_name} НЕ была дана информация про книгу")
            return


@dp.message()
async def echo_message(message: types.Message):
    logger.info(f"Получено сообщение от {message.from_user.full_name}: {message.text}")
    await message.answer("Простите, моё понимание пока ограничено...")

async def main():
    await bot.get_updates(offset=-1)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())