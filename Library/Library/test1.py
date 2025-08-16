import requests

query = "intitle:джейн эйр inauthor:шарлотта бронте"
title1 = "джейн эйр"
author = "шарлотта бронте"
url = "https://www.googleapis.com/books/v1/volumes"

params = {
    'q': query,
    'maxResults': 10
}

response = requests.get(url, params=params)

data = response.json()

for item in data.get('items', []):
    volume_info = item['volumeInfo']
    title = volume_info.get('title', [])
    if title1.lower() == title.lower():
        authors = volume_info.get('authors', [])
        pageCount = volume_info.get('pageCount', 0)
        description = volume_info.get('description', [])
        break

print(f"Название: {title}")
print(f"Авторы: {', '.join(authors)}")
print(f"Количество страниц: {pageCount}")
print(f"Описание: {description}...")
