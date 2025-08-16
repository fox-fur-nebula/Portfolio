data = await resp.json()
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