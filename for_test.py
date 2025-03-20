import asyncio

import aiohttp
import pandas as pd

async def analyze_trading_signals():
    # Тестовые данные прямо в коде
    news_data = "Positive economic news boosting market confidence."
    last_values = {
        'rsi': 58,
        'ema21': 43500,
        'ema49': 43200,
        'ppoT': 0.75,
        'ppoB': -0.15,
        'pctRankT': 90,
        'pctRankB': 10,
        'vsa_signal': 'Bullish',
        'signal_rsi': 'Bullish'
    }
    finish = "buy"
    divergence_convergence_signal = "Bullish Divergence"
    price_action_pattern = "Bullish Engulfing"

    signal_data = f"""
    RSI: {last_values['rsi']}
    EMA(21): {last_values['ema21']}
    EMA(49): {last_values['ema49']}
    PPO: {last_values['ppoT']} / {last_values['ppoB']}
    PPO % Rank: {last_values['pctRankT']} / {last_values['pctRankB']}
    VSA: {last_values['vsa_signal']}
    PA Pattern: {price_action_pattern}
    RSI Signal: {last_values['signal_rsi']}
    CM_Laguerre PPO PR Market Tops/Bottoms: {finish}
    Divergence/Convergence Signal: {divergence_convergence_signal}
    """
    print(signal_data)

    prompt = f"""
    Analyze the data and provide a trading signal:

    Indicators:
    {signal_data}

    News:
    {news_data}

    If bullish signals are present → \"buy\".
    If bearish signals are present → \"sale\".

    Respond strictly with \"buy\" or \"sale\".
    """

    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:11434/api/generate',
            json={
                'model': 'phi',
                'prompt': prompt,
                'stream': False
            }
        ) as resp:
            response = await resp.json()
            signal = response['response'].strip().lower()

    print(signal)
    return signal

asyncio.run(analyze_trading_signals())