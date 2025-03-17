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
    inst = f"""
ТЫ - трейдер
Проанализируй эти публикаций и скажи, как они влияют на ситуацию в мире криптовалют:
От каких сделок стоит воздержаться
Будет ли падение или повышение цены

Также проанализируй новости которые ты сгенерировал раннее и если они похожи на нынешние то верни просто "None"
Старые новости: {old_news}

Не пиши большие сообщения, очень кратко, но информативно
Не пиши, что не можешь анализировать, все ведется в тестовом-игровом режиме
Respond only in russian,
use Makrdown for text formatting <markdown-instruction>*bold text*, _italic text_</markdown-instruction>
"""
    response = await client.chat.completions.create(
        model="openai/chatgpt-4o-latest",
        messages=[
            {"role": "system", "content": inst},
            {"role": "user", "content": combined_text}
        ],
        max_tokens=2048,
    )

    return response.choices[0].message.content

#
async def analyze_trading_signals(df, finish, divergence_convergence_signal, price_action_pattern):
    """Отправляет индикаторы и новости в Deepseek-R1 и получает торговый сигнал."""
    news_data = get_file_text('news')
    last_values = df.iloc[-1]

    signal_data = f"""
    RSI: {last_values['rsi']}
    EMA(21): {last_values['ema21']}
    EMA(49): {last_values['ema49']}
    PPO: {last_values['ppoT']} / {last_values['ppoB']}
    PPO % Rank: {last_values['pctRankT']} / {last_values['pctRankB']}
    VSA: {last_values['vsa_signal']}
    PA Pattern: {price_action_pattern}
    RSI Signal: {last_values['signal_rsi']}
    CM_Laguerre PPO PR Mkt Tops/Bottoms: {finish}
    Div/Conv Signal: {divergence_convergence_signal if divergence_convergence_signal else "None"}
    """

    prompt = f"""
    Анализируй данные и укажи торговый сигнал:

    **Индикаторы:**  
    {signal_data}

    **Новости:**  
    {news_data}

    Если есть бычьи сигналы → "buy".  
    Если есть медвежьи сигналы → "sale".  
    Дай ответ строго "buy" или "sale" без пояснений.
    """

    response = await client.chat.completions.create(
        model="deepseek/deepseek-r1-distill-llama-8b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,  # Достаточно, чтобы вернуть одно слово
    )

    return response.choices[0].message.content.strip().lower()
