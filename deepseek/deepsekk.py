import logging

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

🔹 **Задача**:
Сначала внимательно сравни текущие новости со старыми. 

Если **хотя бы одна текущая новость похожа даже чуть-чуть** (по смыслу, теме, событию, идее, выводам) на старые новости, сразу верни строго `null` без объяснений и форматирования.
Если **текущая новость похожа даже чуть-чуть по выводу на старые публикации** (по смыслу, теме, событию, идее, выводам), сразу верни строго `null` без объяснений и форматирования.

Только если текущие новости полностью уникальны и не похожи на старые, выполни следующий анализ:

Проанализируй новости и оцени их влияние на рынок криптовалют. Ответь на два вопроса:
1. Какие сделки стоит избегать?
2. Будет ли рост или падение цены?

🔹 **Правила возврата `null`**:
Если хоть одна из следующих ситуаций верна, также верни строго `null` без какого-либо форматирования:
- Новость **не влияет** на рынок криптовалют.
- Ты **не уверен**, есть ли влияние.

🔹 **Формат ответа** (если не `null`):
- Отвечай _только_ по делу.
- Используй **Markdown**: <markdown-instruction>*bold text*, _italic text_</markdown-instruction>.
- Используй стикеры при ответе

📌 **Данные для анализа**:

**Старые новости**:
{old_news}

**Текущие новости**:
{combined_text}

**Старые публикации**
{old_public}
"""

    response = await client.chat.completions.create(
        model="openai/chatgpt-4o-latest",
        messages=[{"role": "user", "content": [{"type": "text", "text": inst}]}],
        max_tokens=512,
    )

    return response.choices[0].message.content.strip()

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
    print(signal_data)

    prompt = f"""
    Анализируй данные и укажи торговый сигнал:

    **Индикаторы:**  
    {signal_data}

    **Новости:**  
    {news_data}

    Если есть бычьи сигналы → "buy".  
    Если есть медвежьи сигналы → "sale".  
    Дай ответ строго "buy" или "sale" без пояснений и какого либо форматирования
    """

    response = await client.chat.completions.create(
        model="deepseek/deepseek-r1-distill-llama-8b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,  # Достаточно, чтобы вернуть одно слово
    )

    return response.choices[0].message.content.strip().lower()
