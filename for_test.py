from llama_cpp import Llama
import pandas as pd
from fastapi import FastAPI

app = FastAPI()

# Загружаем модель (работает на CPU)
model = Llama(model_path="model.gguf", n_ctx=2048)

@app.post("/predict")
def predict():

    # Формируем текст для нейросети
    prompt = f"""
    Анализируй данные и укажи торговый сигнал:

    RSI: 44.00039432998614  
    EMA(21): 91.47339715086062  
    EMA(49): 93.20346005535993  
    PPO: 1.2274159208232323 / -1.2274159208232323  
    PPO % Rank: 88.0 / -35.0  
    VSA:  
    PA Pattern: None  
    RSI Signal: Hold  
    CM_Laguerre PPO PR Mkt Tops/Bottoms: sale  
    Div/Conv Signal: bearish_divergence  

    Если есть бычьи сигналы → "buy".  
    Если есть медвежьи сигналы → "sale".  
    Дай ответ строго "buy" или "sale" без пояснений.
    """

    output = model(prompt, max_tokens=10)
    return {"signal": output["choices"][0]["text"].strip().lower()}

