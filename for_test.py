from llama_cpp import Llama
import pandas as pd
from fastapi import FastAPI

app = FastAPI()

# Загружаем модель (работает на CPU)
model = Llama(model_path="model.gguf", n_ctx=2048)

@app.post("/predict")
def predict(data: dict):
    df = pd.DataFrame(data["indicators"])
    last_values = df.iloc[-1]

    # Формируем текст для нейросети
    prompt = f"""
    Анализируй данные и укажи торговый сигнал:

    RSI: {last_values['rsi']}
    EMA(21): {last_values['ema21']}
    EMA(49): {last_values['ema49']}
    PPO: {last_values['ppoT']} / {last_values['ppoB']}
    PPO % Rank: {last_values['pctRankT']} / {last_values['pctRankB']}
    VSA: {last_values['vsa_signal']}
    PA Pattern: {data["price_action_pattern"]}
    RSI Signal: {last_values['signal_rsi']}
    CM_Laguerre PPO PR Mkt Tops/Bottoms: {data["finish"]}
    Div/Conv Signal: {data["divergence_convergence_signal"] if data["divergence_convergence_signal"] else "None"}

    Если есть бычьи сигналы → "buy".  
    Если есть медвежьи сигналы → "sale".  
    Дай ответ строго "buy" или "sale" без пояснений.
    """

    output = model(prompt, max_tokens=10)
    return {"signal": output["choices"][0]["text"].strip().lower()}

