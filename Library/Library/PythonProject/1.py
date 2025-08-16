import datetime
import json
import logging
import os
import random
import string
import time

import aiofiles
import aiohttp
import asyncio

import pycountry
from playwright.async_api import async_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

file_handler = logging.FileHandler("parser.log", encoding='utf-8', errors='replace')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0ZWFtX2lkIjoiMjZiOTBiOTUtZTZmNy00ZWUxLWEwM2UtYTI1MTU2Y2I3NjU1Iiwib3duZXJfaWQiOiIwNzc2YmE4Yy00N2M2LTQ3MTYtODI5Yy0wYWUzZTUwMjY5MTgiLCJ1c2VyX2lkIjoiMDc3NmJhOGMtNDdjNi00NzE2LTgyOWMtMGFlM2U1MDI2OTE4IiwidXNlcm5hbWUiOiJncmV5bTVhZmZAZ21haWwuY29tIiwiaWF0IjoxNzUzNzc2MTM3LCJleHAiOjE3NTYzNjgxMzd9.i3D49I_Fv2xQR3tHYghKAZ5wK64O1CtdvzlSd0t0agE'
GEONIX_API = '986f17b7d7206a4696b06d2be58b6e21'
JSON_FOLDER = 'json_api'


class VisionParser:

    @staticmethod
    async def get_vision_folders():
        headers = {
            'X-Token': TOKEN
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get('https://v1.empr.cloud/api/v1/folders') as resp:
                data = await resp.json()
        logger.info('Получена информация о папках')
        return data

    @staticmethod
    async def get_profile_id(folder_id):
        headers = {
            'X-Token': TOKEN,
            'Content-Type': 'application/json'
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f'https://v1.empr.cloud/api/v1/folders/{folder_id}/profiles?ps=999999') as resp:
                data = await resp.json()
        data['data']['items'].reverse()
        result = []
        for d in data['data']['items']:
            try:
                country_name = d['profile_name'].split('[')[1].split(']')[0]
                if len(country_name) == 2:
                    result.append({'uuid': d['id'], 'geo': d['profile_name'].split('[')[1].split(']')[0]})
                else:
                    continue
            except IndexError as e:
                pass
        return result

    async def start_profile(self, folder_id, profile_id):
        restart = False
        while True:
            headers = {
                "Content-Type": "application/json",
                'X-Token': TOKEN
            }
            json_body = {'args': ['--headless']}
            url = f'http://localhost:3030/start/{folder_id}/{profile_id['uuid']}'
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(url, headers=headers, json=json_body) as resp:
                        data = await resp.json()
                        if data.get('error', ''):
                            logger.error(f'Ошибка: {data["error"]}, при обработке профиля: {data['profile_id']}, '
                                         f'внутри папки: {data['folder_id']}')
                            if 'Proxy error' in data['error']:
                                logger.info('Ошибка прокси. Перезапуск профиля с новыми прокси.')
                                return 'Swap proxy'
                            return None
            except aiohttp.exceptions.ClientConnectorError:
                logger.error(f'Ошибка подключения к профилю: {profile_id['uuid']}, внутри папки: {folder_id}')
                return None

            if not data['port']:
                if not restart:
                    await self.stop_profile(folder_id, profile_id)
                    await asyncio.sleep(10)
                    restart = True
                    continue
                logger.error('Ошибка запуска профиля. Пропуск')
                return None
            logger.info(f"Запущен профиль: {profile_id['uuid']} в папке: {folder_id}")
            return data

    @staticmethod
    async def stop_profile(folder_id, profile_id):
        try:
            headers = {
                'X-Token': TOKEN
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f'http://localhost:3030/stop/{folder_id}/{profile_id["uuid"]}'
                async with session.get(url) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    text = await resp.text()
                    data = {"raw_text": text}

            logger.info(f"Остановлен профиль: {profile_id['uuid']} в папке: {folder_id}")
        except Exception as e:
            logger.error(f'Ошибка при остановке профиля: {e}')

    @staticmethod
    async def get_proxies(folder_id):
        headers = {
            'X-Token': TOKEN,
            'Content-Type': 'application/json'
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f'https://v1.empr.cloud/api/v1/folders/{folder_id}/proxies') as resp:
                data = await resp.json()
        logger.info(f"Получен список прокси для {folder_id}")
        return data

    @staticmethod
    async def add_proxy_to_folder(folder_id, country, proxies, geonix=False, packetstream=False):
        url = f"https://v1.empr.cloud/api/v1/folders/{folder_id}/proxies"
        payload = dict()
        payload['proxies'] = []
        if geonix:
            for proxy in proxies:
                payload['proxies'].append({
                    "proxy_name": f'{country}-{random.choice(string.ascii_uppercase)}{random.randint(1000, 99999)}',
                    "proxy_type": proxy['protocol'],
                    "proxy_ip": proxy['ip_only'],
                    "proxy_port": int(proxy['port_socks']),
                    "proxy_username": proxy['login'],
                    "proxy_password": proxy['password']
                })
        elif packetstream:
            payload['proxies'].append({
                "proxy_name": f'{country}-{random.choice(string.ascii_uppercase)}{random.randint(1000, 99999)} [packetstream]',
                "proxy_type": "SOCKS5",
                "proxy_ip": 'proxy.packetstream.io',
                "proxy_port": 31113,
                "proxy_username": 'datguystunt',
                "proxy_password": f'd06T31wPBrdUA9Xt_country-{proxies}'
            })
        else:
            for proxy in proxies:
                payload['proxies'].append({
                    "proxy_name": f'{country}-{random.choice(string.ascii_uppercase)}{random.randint(1000, 99999)}',
                    "proxy_type": "SOCKS5",
                    "proxy_ip": proxy['server'],
                    "proxy_port": int(proxy['port']),
                    "proxy_username": proxy['username'],
                    "proxy_password": proxy['password']
                })

        headers = {
            'Content-Type': 'application/json',
            'X-Token': TOKEN
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                result = await response.json()
        logger.info(f'Прокси для страны {country} успешно добавлены в папку')

    @staticmethod
    async def add_proxy_to_profile(folder_id, profile_id, proxy):
        url = f"https://v1.empr.cloud/api/v1/folders/{folder_id}/profiles/{profile_id['uuid']}"

        body = {
            'proxy_id': {
                'id': proxy['id']
            }
        }

        headers = {
            'Content-Type': 'application/json',
            'X-Token': TOKEN
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=body) as response:
                result = await response.json()
        logger.info(f"К профилю {profile_id['uuid']} успешно добавлены прокси")


class FacebookParser:
    @staticmethod
    async def get_current_ad_count(page, url, retries: int = 3, delay: float = 2.0) -> int:
        if 'jdelodjlpgkjenhcongcfdcocmjgjbci' in url:
            selector = "span.MuiTypography-root.MuiTypography-body2.MuiListItemText-primary.css-14tqbo1"
        else:
            selector = "span#totalAds"

        for attempt in range(1, retries + 1):
            try:
                span = await page.query_selector(selector)
                if span:
                    if 'jdelodjlpgkjenhcongcfdcocmjgjbci' in url:
                        text = await span.inner_text()
                        count = int(text.split('(')[1].split(')')[0])
                        return count
                    else:
                        count = int(await span.inner_text())
                        return count
                else:
                    logger.warning(f"[{attempt}/{retries}] Элемент не найден: {selector}")
            except (IndexError, ValueError) as e:
                logger.warning(f"[{attempt}/{retries}] Ошибка при разборе текста: {e}")
            except PlaywrightError as e:
                logger.warning(f"[{attempt}/{retries}] Ошибка Playwright при получении рекламы: {e}")
            await asyncio.sleep(delay)

        logger.error(f"Не удалось получить количество рекламы после {retries} попыток.")
        return -1

    async def main_page_parser(self, folder_id, profile_id, port):
        try:
            ad_count = 0
            scroll_time = []

            async with async_playwright() as p:
                try:
                    browser = await p.chromium.connect_over_cdp(endpoint_url=f'http://localhost:{port}')
                except PlaywrightError as e:
                    if "ECONNREFUSED" in str(e):
                        logger.error("Ошибка подключения connect_over_cdp: браузер не запущен или порт недоступен.")
                    else:
                        logger.error(f"Ошибка при подключении через CDP: {e}")
                    return None, None

                context = browser.contexts[0]
                urls = [
                    'chrome-extension://lfoencfnapddpllpjmbpkeciaamhmnic/options.html',
                    'chrome-extension://jdelodjlpgkjenhcongcfdcocmjgjbci/options.html',
                    'https://www.facebook.com/login/',
                    'https://www.facebook.com/marketplace',
                    'chrome-extension://lfoencfnapddpllpjmbpkeciaamhmnic/options.html',
                    'chrome-extension://jdelodjlpgkjenhcongcfdcocmjgjbci/options.html'
                ]
                ads_start = 0
                ads_end = 0

                for i, url in enumerate(urls):
                    page = await context.new_page()

                    async def block_unwanted(route, request):
                        if request.resource_type in ["image", "stylesheet", "font", "media"]:
                            await route.abort()
                        else:
                            await route.continue_()

                    await page.route("**/*", block_unwanted)

                    retry_limit = 3
                    for attempt in range(1, retry_limit + 1):
                        try:
                            await page.goto(url, wait_until='domcontentloaded', timeout=200000)
                            break
                        except PlaywrightTimeoutError:
                            logger.warning(f"[{attempt}/{retry_limit}] Таймаут при переходе на {url}")
                        except PlaywrightError as e:
                            if "net::ERR_SOCKS_CONNECTION_FAILED" in str(e):
                                logger.warning(
                                    f"[{attempt}/{retry_limit}] Ошибка SOCKS подключения при переходе на {url}")
                            else:
                                logger.warning(
                                    f"[{attempt}/{retry_limit}] Другая ошибка Playwright при переходе на {url}: {e}")
                        await asyncio.sleep(2)
                    else:
                        logger.error(f"Не удалось загрузить страницу {url} после {retry_limit} попыток.")
                        await page.close()
                        return None, None

                    await asyncio.sleep(3)

                    if url.startswith('chrome-extension://'):
                        if i < 2:
                            start_ad_count = await self.get_current_ad_count(page, url)
                            if start_ad_count == -1:
                                logger.error('Ошибка при получении начального количества рекламы.')
                                await page.close()
                                return None, None
                            else:
                                ads_start += start_ad_count
                            if i == 1:
                                logger.info(f'Начальное количество собранной рекламы: {ads_start}')
                        else:
                            end_ad_count = await self.get_current_ad_count(page, url)
                            if end_ad_count == -1:
                                logger.error('Ошибка при получении конечного количества рекламы.')
                                await page.close()
                                return None, None
                            else:
                                ads_end += end_ad_count
                            if i == 5:
                                ad_count = ads_end - ads_start
                                logger.info(f'Итоговое количество собранной рекламы: {ad_count}')
                    else:
                        current_page = page.url
                        uuid = profile_id.get('uuid', 'неизвестен')

                        if current_page.startswith('https://www.facebook.com/login/'):
                            logger.error(f'Need relog in to account: {uuid}, папка: {folder_id}.')
                            await page.close()
                            return None, None
                        if current_page.startswith('https://www.facebook.com/checkpoint/'):
                            logger.error(f'Checkpoint для профиля: {uuid}, папка: {folder_id}.')
                            await page.close()
                            return None, None
                        if current_page.startswith('https://www.facebook.com/marketplace/ineligible/'):
                            logger.error(f"Marketplace banned: {uuid}, папка: {folder_id}.")
                            await page.close()
                            return None, None
                        if current_page.startswith('https://www.facebook.com/privacy/consent/'):
                            logger.error(f"Marketplace not created: {uuid}, папка: {folder_id}.")
                            await page.close()
                            return None, None

                        scroll_time.append(await self.human_like_scroll(page))

                    await page.close()

                scroll_time = scroll_time[0] + scroll_time[1]
                return ad_count, scroll_time

        except Exception as e:
            logger.error(f'Ошибка при парсинге: {e}')
            return None, None

    @staticmethod
    async def human_like_scroll(page, min_delay: float = 0.2, max_delay: float = 3):
        scroll_start_time = time.time()
        settings = await Other.get_settings()
        end_time = time.time() + settings['scroll_time'] * 60
        next_reload = time.time() + random.randint(120, 180)

        last_check_time = time.time()

        async def safe_reload(retries=2):
            for attempt in range(retries):
                try:
                    await page.reload()
                    await asyncio.sleep(random.uniform(3, 6))
                    return True
                except PlaywrightTimeoutError:
                    logger.warning(f"Таймаут при reload, попытка {attempt + 1}")
                except PlaywrightError as e:
                    if "net::ERR_SOCKS_CONNECTION_FAILED" in str(e):
                        logger.error(f"Ошибка SOCKS-прокси при reload: {e}")
                    else:
                        logger.error(f"Ошибка при reload: {e}")
                    break
            logger.error("Не удалось обновить страницу после нескольких попыток.")
            return False

        async def safe_get_scroll_height():
            try:
                return await page.evaluate("() => document.body.scrollHeight")
            except PlaywrightError as e:
                logger.error(f"Ошибка при получении scrollHeight: {e}")
                return None

        last_scroll_height = await safe_get_scroll_height()
        if last_scroll_height is None:
            return 0

        while time.time() < end_time:
            now = time.time()

            current_scroll_height = await safe_get_scroll_height()
            if current_scroll_height is None:
                return int(time.time() - scroll_start_time)

            if current_scroll_height == last_scroll_height:
                if now - last_check_time > 20:
                    logger.info("Контент не обновляется более 20 секунд. Обновляем страницу.")
                    if not await safe_reload():
                        await page.close()
                        return int(time.time() - scroll_start_time)
                    last_check_time = time.time()
                    last_scroll_height = await safe_get_scroll_height() or 0
                    continue
            else:
                last_check_time = now
                last_scroll_height = current_scroll_height

            if now >= next_reload:
                logger.info("Страница обновляется по таймеру.")
                if not await safe_reload():
                    await page.close()
                    return int(time.time() - scroll_start_time)
                last_check_time = time.time()
                last_scroll_height = await safe_get_scroll_height() or 0
                next_reload = time.time() + random.randint(120, 180)
                continue

            scroll_distance = random.randint(200, 1000)
            direction = 1 if random.random() > 0.1 else -1
            scroll_script = f"window.scrollBy(0, {direction * scroll_distance})"
            try:
                await page.evaluate(scroll_script)
            except PlaywrightError as e:
                logger.error(f"Ошибка при скролле страницы: {e}")
                return int(time.time() - scroll_start_time)

            await asyncio.sleep(random.uniform(min_delay, max_delay))

        await asyncio.sleep(random.uniform(1.0, 3.0))
        return int(time.time() - scroll_start_time)


class ApiClass:
    @staticmethod
    async def api_get_profiles(parallel_profiles, api_url="https://mtw.rest/api/v2/accounts/cron__farm.php",
                               token="apwCzux8B468HUbcah6ps0U5dhjJ5Z0lJsRK4R2wGhXUIz0mwHtlcbXo5E2L4RwQ"):
        logger.info(f"Попытка получения профилей.")

        headers = {
            'X-Token': token,
            'Content-Type': 'application/json'
        }
        try:
            i = 0
            profiles = []
            async with aiohttp.ClientSession() as session:
                while i < parallel_profiles:
                    async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                                           ) as response:
                        if response.status != 200:
                            logger.error(f"Ошибка API: HTTP {response.status}")
                            return None

                        result = await response.json()
                        if result['success']:
                            logger.info(
                                f'Получен профиль с id: {result['data']['uuid']}, со страной: {result["data"]["geo"]}')
                            profiles.append(result['data'])
                    i += 1
                return profiles
        except Exception as e:
            logger.error(f'Ошибка при получении профилей: {e}')

    @staticmethod
    async def generate_proxies(country_code_alpha: str, type: str = 'socks5', provider: str = 'nsocks',
                               attempts: int = 0,
                               provider_switched: bool = False):

        if attempts >= 5:
            if not provider_switched:
                attempts = 0
                provider_switched = True

                logger.debug("Trying to switch provider")

                return await ApiClass.generate_proxies(country_code_alpha, type, "swift", attempts, provider_switched)
            else:
                logger.error("Не удалось получить прокси после 5 попыток")
                return None

        if provider.lower() == "nsocks":
            proxies = await ApiClass.api_get_nsocks(
                country_code_alpha)

            logger.info("Получение данных из NSOCKS")

            if not proxies:
                logger.error(f"Не удалось получить прокси из nsocks")
                return await ApiClass.generate_proxies(country_code_alpha, type, "packetstream", 0)

            return proxies

        country_name = await ApiClass.get_country_proxy(country_code_alpha)  # Тоже синхронная функция
        random_session = await ApiClass.generate_random_word(random.randint(5, 10))

        if country_name is None:
            provider = "swift"

        if provider.lower() == "packetstream":
            port = "31113" if "socks5" in type else "31112"
            server = "proxy.packetstream.io"
            username = 'datguystunt'
            password = f'd06T31wPBrdUA9Xt_country-{country_name}_session-{random_session}'
        else:  # swiftproxy
            port = "12000" if "socks5" in type else "10000"
            server = "residential.swiftproxy.io"
            username = f"mtwfarmbot-country-{country_code_alpha.lower()}-session-{random_session}-lifetime-300"
            password = "2fd3edfd-d855-4627-9ccf-b4ea9bf6b5d3"

        proxy_string = f"{server}:{port}:{username}:{password}"

        proxy_url = f"{username}:{password}@{server}:{port}"
        scheme = "socks5" if "socks5" in type else "http"

        proxy = f"{scheme}://{proxy_url}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://ip-api.com/json", proxy=proxy,
                                       timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()
                    logger.info(f"Attempt {attempts + 1}: Proxy IP info:", data)

                    if data.get('countryCode', '').upper() == country_code_alpha.upper():
                        return proxy_string
                    else:
                        logger.error(
                            f"Страна не совпадает. Ожидалось: {country_code_alpha}, Получено: {data.get('countryCode')}")
                        return await ApiClass.generate_proxies(country_code_alpha, type, provider, attempts + 1,
                                                               provider_switched)
        except Exception as e:
            logger.error(f"Ошибка при проверке прокси: {str(e)}")
            return await ApiClass.generate_proxies(country_code_alpha, type, provider, attempts + 1, provider_switched)

    @staticmethod
    async def get_country_proxy(country_code: str) -> str:
        countries = {
            "RND": "Random",
            "US": "UnitedStates",
            "CA": "Canada",
            "AF": "Afghanistan",
            "AL": "Albania",
            "DZ": "Algeria",
            "AR": "Argentina",
            "AM": "Armenia",
            "AW": "Aruba",
            "AU": "Australia",
            "AT": "Austria",
            "AZ": "Azerbaijan",
            "BS": "Bahamas",
            "BH": "Bahrain",
            "BD": "Bangladesh",
            "BY": "Belarus",
            "BE": "Belgium",
            "BA": "BosniaandHerzegovina",
            "BR": "Brazil",
            "VG": "BritishVirginIslands",
            "BN": "Brunei",
            "BG": "Bulgaria",
            "KH": "Cambodia",
            "CM": "Cameroon",
            "CL": "Chile",
            "CN": "China",
            "CO": "Colombia",
            "CR": "CostaRica",
            "HR": "Croatia",
            "CU": "Cuba",
            "CY": "Cyprus",
            "CZ": "Czechia",
            "DK": "Denmark",
            "DO": "DominicanRepublic",
            "EC": "Ecuador",
            "EG": "Egypt",
            "SV": "ElSalvador",
            "EE": "Estonia",
            "ET": "Ethiopia",
            "FI": "Finland",
            "FR": "France",
            "GE": "Georgia",
            "DE": "Germany",
            "GH": "Ghana",
            "GR": "Greece",
            "GT": "Guatemala",
            "GY": "Guyana",
            "JO": "HashemiteKingdomofJordan",
            "HK": "HongKong",
            "HU": "Hungary",
            "IN": "India",
            "ID": "Indonesia",
            "IR": "Iran",
            "IQ": "Iraq",
            "IE": "Ireland",
            "IL": "Israel",
            "IT": "Italy",
            "JM": "Jamaica",
            "JP": "Japan",
            "KZ": "Kazakhstan",
            "KE": "Kenya",
            "XK": "Kosovo",
            "KW": "Kuwait",
            "LV": "Latvia",
            "LI": "Liechtenstein",
            "LU": "Luxembourg",
            "MK": "Macedonia",
            "MG": "Madagascar",
            "MY": "Malaysia",
            "MU": "Mauritius",
            "MX": "Mexico",
            "MN": "Mongolia",
            "ME": "Montenegro",
            "MA": "Morocco",
            "MZ": "Mozambique",
            "MM": "Myanmar",
            "NP": "Nepal",
            "NL": "Netherlands",
            "NZ": "NewZealand",
            "NG": "Nigeria",
            "NO": "Norway",
            "OM": "Oman",
            "PK": "Pakistan",
            "PS": "Palestine",
            "PA": "Panama",
            "PG": "PapuaNewGuinea",
            "PY": "Paraguay",
            "PE": "Peru",
            "PH": "Philippines",
            "PL": "Poland",
            "PT": "Portugal",
            "PR": "PuertoRico",
            "QA": "Qatar",
            "LT": "RepublicofLithuania",
            "MD": "RepublicofMoldova",
            "RO": "Romania",
            "RU": "Russia",
            "SA": "SaudiArabia",
            "SN": "Senegal",
            "RS": "Serbia",
            "SC": "Seychelles",
            "SG": "Singapore",
            "SK": "Slovakia",
            "SI": "Slovenia",
            "SO": "Somalia",
            "ZA": "SouthAfrica",
            "KR": "SouthKorea",
            "ES": "Spain",
            "LK": "SriLanka",
            "SD": "Sudan",
            "SR": "Suriname",
            "SE": "Sweden",
            "CH": "Switzerland",
            "SY": "Syria",
            "TW": "Taiwan",
            "TJ": "Tajikistan",
            "TH": "Thailand",
            "TT": "TrinidadandTobago",
            "TN": "Tunisia",
            "TR": "Turkey",
            "UG": "Uganda",
            "UA": "Ukraine",
            "AE": "UnitedArabEmirates",
            "GB": "UnitedKingdom",
            "UZ": "Uzbekistan",
            "VE": "Venezuela",
            "VN": "Vietnam",
            "ZM": "Zambia"
        }

        return countries.get(country_code.upper(), None)

    @staticmethod
    async def generate_random_word(length):
        letters = string.ascii_letters
        return ''.join(random.choice(letters) for i in range(length))

    @staticmethod
    async def api_get_nsocks(country, api_url="https://mtw.rest/proxies/get.php",
                             token="pPQnJFbDke6m4fW7XsLy9z5cRtYhAg2v"):

        logger.info(f"Попытка запроса прокси для страны: {country}.")

        headers = {
            'X-Token': token,
            'Content-Type': 'application/json'
        }

        data = {
            'type': 'socks5',
            'country': country,
            'limit': 999
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        api_url,
                        headers=headers,
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка API: HTTP {response.status}")
                        return None

                    result = await response.json()

                    if not result.get('success') or not result.get('data'):
                        logger.error(f"Ошибка API: {result.get('message', 'Неизвестная ошибка')}")
                        return None
                    proxies = []
                    for proxy in result.get('data'):
                        proxy_data = proxy['proxy_data']

                        parts = proxy_data.split(':')

                        if len(parts) < 2:
                            return False

                        server = parts[0]
                        port = parts[1]
                        username = parts[2] if len(parts) > 2 else ""
                        password = parts[3] if len(parts) > 3 else ""

                        proxies.append({'server': server, 'port': port, 'username': username, 'password': password})
                    return proxies

        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения: {e}")
            return None
        except json.JSONDecodeError:
            logger.error("Ошибка при чтении JSON-ответа")
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return None

    @staticmethod
    async def send_data(country_code, profile_uuid, connection='VPN|packetstream'):
        url = "https://mtw.rest/api/add_queue.php"

        data = {
            'profile_id': profile_uuid,
            'alpha2': country_code,
            'connection': connection
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        logger.info(f'Данные успешно отправлены на сервер')
                        logger.debug(
                            f'Сообщение при отправке данных на сервер, для профиля: {profile_uuid}: {await response.text()}')
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None

    @staticmethod
    async def send_statistic(ad_count, scroll_time, country, profile_uuid, connection='VPN|packetstream'):
        url = "https://mtw.rest/api/stats/send.php"

        data = {
            'country_code': country,
            'profile_uuid': profile_uuid,
            'result': ad_count,
            'duration': scroll_time,
            'provider': connection
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        logger.info(f'Данные статистики успешно отправлены на сервер')
                        logger.debug(
                            f'Сообщение при отправке данных на сервер, для профиля: {profile_uuid}: {await response.text()}')
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None

    @staticmethod
    async def update_last_farm(uuid, last_farm=None):
        url = "https://mtw.rest/api/accounts/upd.php"

        if last_farm is None:
            last_farm = datetime.datetime.now().strftime("%Y-%m-%d")

        data = {
            "uuid": uuid,
            "last_farm": last_farm
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f'Профиль {uuid} успешно завершил работу')
                        return await response.json()
                    else:
                        logger.error(f"Error: Status: {response.status}, Text: {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None

    @staticmethod
    async def current_json(current_profiles):
        async with aiofiles.open(f'{JSON_FOLDER}/current_profiles.json', 'w', encoding='utf-8') as f:
            json_data = json.dumps(current_profiles, ensure_ascii=False, indent=4)
            await f.write(json_data)

    @staticmethod
    async def geonix_proxies():
        types = ('ipv4', 'isp')
        proxies = dict()
        for t in types:
            url = f"https://geonix.com/personal/api/v1/{GEONIX_API}/proxy/list/{t}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    proxies[t] = data['data']['items']
        return proxies


class Other:
    @staticmethod
    async def create_folders():
        os.makedirs(JSON_FOLDER, exist_ok=True)
        settings = {'scroll_time': 10, 'parallel_profiles': 3, 'pause': False}
        async with aiofiles.open(f'{JSON_FOLDER}/settings.json', 'w', encoding='utf-8') as f:
            json_data = json.dumps(settings, ensure_ascii=False, indent=4)
            await f.write(json_data)

    @staticmethod
    async def get_settings():
        async with aiofiles.open(f'{JSON_FOLDER}/settings.json', 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)

    @staticmethod
    async def get_good_proxies(vision, api, folder_id, country, packetstream=False):
        proxies = await api.geonix_proxies()
        country_full = pycountry.countries.get(alpha_2=country.upper())
        proxies_list = list()
        if country_full:
            for proxy in proxies:
                proxies_list.extend(
                    list(filter(lambda proxy_item: proxy_item['country_alpha3'] == country_full.alpha_3,
                                proxies[proxy])))
                if len(proxies_list) == 0:
                    proxies_list.extend(list(filter(lambda proxy_item: proxy_item['country'] == country_full.name,
                                                    proxies[proxy])))
            if len(proxies_list) > 0:
                await vision.add_proxy_to_folder(folder_id, country, proxies_list, geonix=True)
                return 'geonix'
        if len(proxies_list) == 0:
            proxies_list = await api.generate_proxies(country)
            if proxies_list is not None:
                await vision.add_proxy_to_folder(folder_id, country, proxies_list)
                return 'API'
            if proxies_list is None and packetstream is False:
                await vision.add_proxy_to_folder(folder_id, country, f'_country-{country_full.name}', packetstream=True)
                return 'PACKETSTREAM'
        return ''

    @staticmethod
    async def get_good_and_packetstream_proxy(country, vision, folder_id):
        good_proxies = await vision.get_proxies(folder_id)
        good_proxies = list(
            filter(lambda proxy_item: proxy_item['proxy_name'].split('-')[0] == country, good_proxies['data']))
        packetstream_proxy = [proxy for proxy in good_proxies if (proxy['proxy_port'] in (31111, 31112, 31113, 12000) and proxy['profiles'] == 0)]
        good_proxies = [proxy for proxy in good_proxies if proxy['proxy_port'] not in (31111, 31112, 31113, 12000)]
        random.shuffle(good_proxies)
        random.shuffle(packetstream_proxy)
        return good_proxies, packetstream_proxy


async def main():
    vision = VisionParser()
    api = ApiClass()
    other_func = Other()
    # folders_data = await vision.get_vision_folders()
    folder_id = '39cfb98d-5058-4798-bd90-882ea34a891a'
    logger.info(f'Обработка папки: {folder_id}')
    if not os.path.isdir(JSON_FOLDER):
        await Other.create_folders()
    while True:
        # api_profile_data = await vision.get_profile_id(folder_id)
        # BACK
        settings = await Other.get_settings()
        if settings['pause']:
            logger.info('Код отправлен на паузу благодаря настройкам settings.json')
            while True:
                await asyncio.sleep(5)
                settings = await Other.get_settings()
                if not settings['pause']:
                    logger.info('Пауза была снята. Продолжение парсинга')
                    break
        api_profile_data = await api.api_get_profiles(settings['parallel_profiles'])
        if len(api_profile_data) == 0 or api_profile_data is None:
            logger.info('Закончились профили для обработки. Отдых 30 минут.')
            await asyncio.sleep(1800)
            continue
        await api.current_json(api_profile_data)
        batches = [api_profile_data[i:i + settings['parallel_profiles']] for i in range(0, len(api_profile_data),
                                                                                        settings['parallel_profiles'])]
        for batch_number, batch in enumerate(batches, start=1):
            logger.info(f"Обработка батча {batch_number}/{len(batches)}.")
            batch_start_time = time.time()
            tasks = []
            for profile_id in batch:
                task = asyncio.create_task(
                    start_process(vision, api, folder_id, profile_id))
                tasks.append(task)
            await asyncio.gather(*tasks)

            batch_elapsed_time = time.time() - batch_start_time
            formatted_batch_time = str(datetime.timedelta(seconds=batch_elapsed_time))
            logger.info(
                f"Батч {batch_number}/{len(batches)} обработан за {formatted_batch_time}.")


async def start_process(vision, api, folder_id, profile_id):
    semaphore = asyncio.Semaphore()
    async with semaphore:
        fb = FacebookParser()
        country = profile_id['geo']
        good_proxies, packetstream_proxy = await Other.get_good_and_packetstream_proxy(country, vision, folder_id)
        type_proxy = ''
        if len(good_proxies) == 0:
            packetstream_found = False if len(packetstream_proxy) == 0 else True
            type_proxy = await Other.get_good_proxies(vision, api, folder_id, country, packetstream=packetstream_found)
            if type_proxy != '':
                logger.info(f'Для профиля запрошены {type_proxy} прокси.')
            elif type_proxy == '' and packetstream_found is False:
                logger.info('Рабочие прокси не найдены. Пропуск профиля.')
                return
        else:
            logger.info(f'В Vision уже добавлены geonix|API прокси для страны {country}')
        if len(good_proxies) > 0:
            pass
        elif len(good_proxies) == 0 and type_proxy in ('geonix', 'API'):
            good_proxies, packetstream_proxy = await Other.get_good_and_packetstream_proxy(country, vision, folder_id)
            logger.info(f'Для страны {country} найдены и добавлены {type_proxy} прокси.')
        elif len(packetstream_proxy) > 0:
            logger.info(f'Для страны {country} существуют только packetstream прокси')
        try_proxy = 1
        stop = False
        if len(good_proxies) > 0:
            proxies = good_proxies
        else:
            proxies = packetstream_proxy
            try_proxy = 2
            logger.info('Попытка запуска профиля с packetstream прокси')
        while not stop:
            for proxy in proxies:
                await vision.add_proxy_to_profile(folder_id, profile_id, proxy)
                start_data = await vision.start_profile(folder_id, profile_id)
                if start_data != 'Swap proxy':
                    stop = True
                    break
            else:
                logger.info('Рабочие прокси не найдены.')
                if try_proxy == 1:
                    logger.info('Повторная попытка с packetstream прокси')
                    proxies = packetstream_proxy
                    try_proxy += 1
                else:
                    return
        if not start_data:
            return
        try:
            port = start_data['port']
        except TypeError:
            logger.info(f'Ошибка порта. Порт: {start_data}')
        count_collected_ad, scroll_time = await fb.main_page_parser(folder_id, profile_id, port)
        if count_collected_ad is None:
            await vision.stop_profile(folder_id, profile_id)
            return
        await vision.stop_profile(folder_id, profile_id)
        await api.send_statistic(count_collected_ad, scroll_time, country, profile_id['uuid'])
        await api.send_data(country, profile_id['uuid'])
        await api.update_last_farm(profile_id['uuid'])


if __name__ == '__main__':
    asyncio.run(main())
