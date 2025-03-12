def get_news_text():
    with open("news/news.txt", "r", encoding="utf-8") as f:
        news = f.read().strip()  # Убираем лишние пробелы в начале и в конце строки
        if not news:  # Если файл пустой
            return None
        return news


def set_news_text(new_text):
    with open(f"news/news.txt", "w", encoding="utf-8") as f:
        f.write(str(new_text))
