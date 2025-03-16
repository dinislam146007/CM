def get_file_text(file_name):
    with open(f"news/{file_name}.txt", "r", encoding="utf-8") as f:
        news = f.read().strip()  # Убираем лишние пробелы в начале и в конце строки
        if not news:  # Если файл пустой
            return None
        return news

def set_file_text(file_name: str, new_text:str):
    with open(f"news/{file_name}.txt", "w", encoding="utf-8") as f:
        f.write(str(new_text))