from news import get_file_text
import json
from openai import AsyncOpenAI
from config import config

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config.deepseek_api
)

#
async def analyze_with_deepseek(messages) -> str:
    combined_text = "\n".join(msg if msg is not None else "" for msg in messages)
    old_news = get_file_text('old_news')
    old_public = get_file_text('old_public')

    inst = f"""
Ты - трейдер, специалист по криптовалютам.

🔹 Задача:
Сначала внимательно проверь текущие новости и старые.

Если текущая новость полностью идентична (точная копия текста или дословно совпадает по всем ключевым деталям, без каких-либо изменений или обновлений), сразу верни строго null и объясни почему ты это вернул.

Обращай внимание на новости, содержащие обновления, изменения дат, уточнения деталей, новые данные и т.д. Такие новости не блокируй и обязательно анализируй.
Удели особое внимание новостям, связанным с Dogecoin, и упоминаниям DOGE в тексте.

Также удели особое внимание новостям, в которых содержится информация, связанная с ФРС, повышением или понижением ставок, изменением ДКП (Денежно-Кредитной политики).  
Повышение или понижение ставок, смягчение ДКП оказывают прямое воздействие на рынок криптовалют и традиционные финансовые рынки.

Особое внимание удели:
- 🐕🐕🐕 Dogecoin (DOGE)
- 💸⚠️‼️ новостям про ФРС, ставки, изменение ДКП (Денежно-Кредитной политики).

Проанализируй новости и оцени их влияние на рынок криптовалют. Ответь на два вопроса:
1. Какие сделки стоит избегать?
2. Будет ли рост или падение цены?

🔹 Если новость ещё НЕ подтверждена (например, законопроект не принят или решение не окончательное), укажи специальный стикер с вопросом:
- ❓🔰 для возможного, но не подтверждённого роста
- ❓🔻 для возможного, но не подтверждённого падения

🔹 **Возврат null только если**:
- Новость идентична старой.
- Новость никак не влияет на рынок криптовалют.

🔹 **Формат ответа** (если не null):
- Без вводных слов ("Ответ:", "Анализ показал:" и т.д.).
- Используй Markdown: *bold text*, _italic text_.
- Используй стикеры.
- Укажи тему новости.

🔸 **Иконки для новостей:**
- 🔰🔰🔰 рост
- 🔻🔻🔻 падение
- ❓ нейтрально
- 💸⚠️‼️ ФРС
- ⚠️‼️🔻🔻🔻 Делистинг токенов (строго такое оформление)

🔸 **Выделенные токены:**
- 🐕🐕🐕 DOGE
- 💎 Ethereum (ETH)

Пример:
"
🔰🔰🔰

🔥*Тема:*

📌 Затронутые токены:
"

📌 **Данные для анализа**:

**Старые новости**:
{old_news}

🔸 **В конце генерации** укажи конкретные токены, затронутые новостью.
"""

    response = await client.chat.completions.create(
        model="openai/chatgpt-4o-latest",
        messages=[
            {"role": "system", "content": inst},
            {"role": "user", "content": combined_text}
        ],
        max_tokens=2048,
    )

    return response.choices[0].message.content.strip()

#


async def analyze_trading_signals(df,
                                  finish,
                                  divergence_convergence_signal,
                                  price_action_pattern,
                                  symbol,
                                  timeframe,
                                  buy_price
                            ):
    news_data = get_file_text('old_news')
    last_values = df.iloc[-1]

    signal_data = f"""
    Buy_price: {buy_price}
    RSI: {last_values['rsi']}
    EMA(21): {last_values['ema21']}
    EMA(49): {last_values['ema49']}
    PPO: {last_values['ppoT']} / {last_values['ppoB']}
    PPO % Rank: {last_values['pctRankT']} / {last_values['pctRankB']}
    VSA: {last_values['vsa_signal']}
    PA Pattern: {price_action_pattern}
    RSI Signal: {last_values['signal_rsi']}
    CM_Laguerre PPO PR Market Tops/Bottoms: {finish}
    Divergence/Convergence Signal: {divergence_convergence_signal if divergence_convergence_signal else "None"}
    """

    prompt = f"""
    Анализируя предоставленные рыночные данные и новости, сформируйте подробный торговый сигнал в следующем JSON-формате. Ответ должен быть исключительно на русском языке:

    {{
        "pair": "{symbol}",
        "signal_type": "Long 🔰 или Short 🔻",
        "timeframe": "{timeframe}",
        "entry_point": "цена входа $",
        "take_profit": "цена тейк-профита $",
        "stop_loss": "цена стоп-лосса $",
        "reason": "
        Ответь на 2 вопроса:
        1. По каким конкретным причинам ты поставил тейк-профит 
        2. По каким конкретным причинам ты поставил стоп лос 
        ",
        "timestamp": "текущая дата и время в формате dd-mm-YYYY HH:MM"
    }}
    Тейк профит и стоп лос ты должен ставить опираясь на предоставленную информацию с сигналов и новостей
    Определите, являются ли сигналы бычьими (Long) или медвежьими (Short), установите реалистичные цены для входа, тейк-профита и стоп-лосса, а также в ключе "reason" предоставьте обоснование выбранных уровней.

    Ответ должен быть только в виде JSON.
    Response only Russia and Use Markdown for text formatting *bold text*, _italic text_
    """

    response = await client.chat.completions.create(
        model="openai/gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "news:"+ news_data + "indicators"+signal_data}
        ],
        max_tokens=512,
    )

    raw_response = response.choices[0].message.content.strip()
    try:
        signal_json = json.loads(raw_response)
    except json.JSONDecodeError:
        print("❌ Ошибка парсинга JSON от модели:", raw_response)
        return None

    return signal_json
