from llama_cpp import Llama
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Загружаем модель
model = Llama(model_path="model.gguf", n_ctx=2048)

# Определяем формат запроса
class RequestData(BaseModel):
    rsi: float
    ema21: float
    ema49: float
    ppo: tuple
    ppo_rank: tuple
    vsa: str
    pa_pattern: str
    rsi_signal: str
    cm_laguerre: str
    div_conv_signal: str

@app.post("/predict")
def predict(data: RequestData):
    # Формируем промпт
    prompt = f"""
Ты должен строго ответить либо "buy", либо "sale" и ничего больше.
Никаких других слов, пояснений, комментариев.

    RSI: {data.rsi}  
    EMA(21): {data.ema21}  
    EMA(49): {data.ema49}  
    PPO: {data.ppo[0]} / {data.ppo[1]}  
    PPO % Rank: {data.ppo_rank[0]} / {data.ppo_rank[1]}  
    VSA: {data.vsa}  
    PA Pattern: {data.pa_pattern}  
    RSI Signal: {data.rsi_signal}  
    CM_Laguerre PPO PR Mkt Tops/Bottoms: {data.cm_laguerre}  
    Div/Conv Signal: {data.div_conv_signal}  

    Если есть бычьи сигналы → "buy".  
    Если есть медвежьи сигналы → "sale".  
    Дай ответ строго "buy" или "sale" без пояснений.
    """

    # Запрос в модель
    output = model(prompt, echo=False)

    # Извлекаем ответ
    response_text = output["choices"][0]["text"].strip().lower()

    return {"signal": response_text}
