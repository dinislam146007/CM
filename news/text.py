import json
import os

def get_file_text(file_name):
    file_path = f"news/{file_name}.json"
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def set_file_text(file_name: str, new_text: str):
    file_path = f"news/{file_name}.json"

    # Загружаем старые данные
    news_list = get_file_text(file_name)

    # Добавляем новую новость
    news_list.append(new_text.strip())

    # Оставляем только последние 10
    news_list = news_list[-10:]

    # Сохраняем
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

