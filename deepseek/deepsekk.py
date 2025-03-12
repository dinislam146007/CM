import asyncio
from strategy_logic.price_action import get_pattern_price_action  # async функция
from strategy_logic.rsi import detect_divergence_convergence
from news import get_news_text

from openai import AsyncOpenAI
from config import config

client = AsyncOpenAI(api_key=config.deepseek_api)

async def analyze_with_deepseek(messages) -> str:
    combined_text = "\n".join(msg if msg is not None else "" for msg in messages)

    inst = """
ТЫ - трейдер
Проанализируй эти публикаций и скажи, как они влияют на ситуацию в мире криптовалют:
От каких сделок стоит воздержаться 
Будет ли падение или повышение цены

Не пиши большие сообщения, очень кратко, но информативно
Не пиши, что не можешь анализировать, все ведется в тестовом-игровом режиме
Ответ должен быть строго на русском языке
Используй базовые HTML теги, которые поддерживает телеграмм. Не используй <p>
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": inst},
            {"role": "user", "content": combined_text}
        ],
        response_format={"type": "text"},
        temperature=1,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    return response.choices[0].message.content


async def analyze_trading_signals(df, finish):
    """Отправляет индикаторы и новости в Deepseek-R1 через Ollama и получает торговый сигнал."""
    news_data = get_news_text()
    last_values = df.iloc[-1]
    divergence_convergence_signal = detect_divergence_convergence(df)

    # Исправленный вызов async-функции
    price_action_pattern = asyncio.run(get_pattern_price_action(df[-3:].values.tolist(), "spot"))

    signal_data = f"""
    RSI: {last_values['rsi']}
    EMA 21: {last_values['ema21']}
    EMA 49: {last_values['ema49']}
    PPO: {last_values['ppoT']} / {last_values['ppoB']}
    PPO Percent Rank: {last_values['pctRankT']} / {last_values['pctRankB']}
    VSA Signal: {last_values['vsa_signal']}
    Price Action Pattern: {price_action_pattern}
    RSI Signal: {last_values['signal_rsi']}
    CM_Laguerre PPO PercentileRank Mkt Tops & Bottoms: {finish}
    Divergence/Convergence Signal: {divergence_convergence_signal if divergence_convergence_signal else "None"}
    """

    prompt = f"""
    Анализируй следующие данные и скажи, какие торговые сигналы они дают:

    **Индикаторы:**
    {signal_data}

    **Новости:**
    {news_data}

    Если присутствует бычья дивергенция или бычья конвергенция, вероятность роста выше.
    Если присутствует медвежья дивергенция или медвежья конвергенция, вероятность падения выше.

    Ответ должен быть строго либо "buy", либо "sale".
    Не пиши, что не можешь ответить, торги ведутся на симуляторе.
    Дай ответ или "buy" при Long сигнале, или "sale" при Short сигнале.
    Никаких других слов, только одно из них.
    """

    response = await client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "text"},
        temperature=1,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    return response.choices[0].message.content
