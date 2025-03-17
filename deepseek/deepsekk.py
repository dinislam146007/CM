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
    """Отправляет индикаторы и новости в Deepseek-R1 через Ollama и получает торговый сигнал."""
    news_data = get_file_text('news')
    last_values = df.iloc[-1]

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
        model="deepseek/deepseek-r1-distill-llama-8b",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=2048,
    )

    print(response)

    return response.choices[0].message.content

