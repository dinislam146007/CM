import re
import requests


def get_usdt_pairs() -> list[str]:
    # URL для получения списка торговых инструментов
    url = "https://api.bybit.com/v5/market/instruments-info"

    # Параметры запроса
    params = {
        "category": "spot"  # Или "linear" для деривативов
    }

    # Список пар, которые нужно исключить
    excluded_pairs = {"BTC3USDT", "ETH3USDT"}

    try:
        # Отправляем запрос к API
        response = requests.get(url, params=params)
        response.raise_for_status()  # Проверяем, что запрос выполнен успешно

        # Разбираем JSON-ответ
        data = response.json()

        if data['retCode'] == 0:  # Проверка успешного выполнения
            usdt_pairs = []
            for instrument in data['result']['list']:
                base_coin = instrument['baseCoin']
                pair = f"{base_coin}USDT"

                # Условие фильтрации
                if (
                        instrument['quoteCoin'] == "USDT" and
                        not is_stablecoin(base_coin) and
                        pair not in excluded_pairs and
                        not is_leverage_pair(base_coin)  # Исключаем пары с числом
                ):
                    usdt_pairs.append(pair)
            return usdt_pairs
        else:
            print("Ошибка API:", data['retMsg'])
            return []
    except requests.RequestException as e:
        print("Ошибка сети или API:", e)
        return []


def is_stablecoin(base_coin):
    """
    Определяет, является ли монета стейблкоином.
    """
    # Если в названии монеты есть признаки стейблкоина
    stablecoin_keywords = {"USD", "USDT", "USDC", "DAI", "BUSD", "TUSD", "PAX", "GUSD", "UST", "HUSD"}
    for keyword in stablecoin_keywords:
        if keyword in base_coin:
            return True
    return False


def is_leverage_pair(base_coin):
    """
    Определяет, является ли монета парой с левереджем.
    """
    # Проверяем, содержит ли базовая монета цифры или суффиксы левереджа
    return bool(re.search(r'\d+[A-Z]*$', base_coin))
# print(get_usdt_pairs())