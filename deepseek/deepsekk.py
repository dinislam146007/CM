from mimetypes import inited

import aiohttp

from news import get_file_text

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
    news_data = get_file_text('news')
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
    Analyze the provided market data and news, then generate a detailed trading signal in the following JSON format:

    {{
        "pair": "{symbol}",
        "signal_type": "Long 🔰" or "Short 🔻",
        "timeframe": "{timeframe}",
        "entry_point": "entry price$",
        "take_profit": "TP price$",
        "stop_loss": "SL price$",
        "timestamp": "current date and time in dd-mm-YYYY HH:MM format"
    }}

    Indicators:
    {signal_data}

    News:
    {news_data}

    Determine if the signals are bullish (Long) or bearish (Short), set realistic entry, take-profit, and stop-loss prices accordingly.

    Respond strictly with the JSON only.
    """

    response = await client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        max_tokens=512,
    )

    return response.choices[0].message.content.strip()
