from datetime import datetime

days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']

now = datetime.now()
weekday_ru = days[now.weekday()]
day_str = now.strftime('%d')

formatted_date = f"{weekday_ru} {day_str}"

print(formatted_date)
