-- Расширенная схема для отслеживания стратегий и статистики
-- Добавляемые колонки к существующей таблице orders

-- 1. ДЕТАЛИЗАЦИЯ СИГНАЛОВ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_strength REAL; -- Сила сигнала (0.0-1.0)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_confidence REAL; -- Уверенность в сигнале (0.0-1.0)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_combination TEXT; -- Комбинация стратегий "CM+RSI+PA"

-- 2. РЫНОЧНЫЕ УСЛОВИЯ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS market_condition TEXT; -- "bullish", "bearish", "sideways"
ALTER TABLE orders ADD COLUMN IF NOT EXISTS volatility_level TEXT; -- "low", "medium", "high"
ALTER TABLE orders ADD COLUMN IF NOT EXISTS volume_profile TEXT; -- "low", "normal", "high"

-- 3. ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ (значения на момент входа)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS rsi_value REAL; -- Значение RSI на момент входа
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cm_ppo_value REAL; -- Значение CM PPO
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ema_fast REAL; -- Быстрая EMA
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ema_slow REAL; -- Медленная EMA
ALTER TABLE orders ADD COLUMN IF NOT EXISTS atr_value REAL; -- ATR на момент входа

-- 4. СТАТИСТИКА ВЫПОЛНЕНИЯ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS time_to_tp_minutes INTEGER; -- Время до достижения TP (в минутах)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS time_to_sl_minutes INTEGER; -- Время до достижения SL (в минутах)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS max_profit_percent REAL; -- Максимальная прибыль во время сделки
ALTER TABLE orders ADD COLUMN IF NOT EXISTS max_drawdown_percent REAL; -- Максимальная просадка

-- 5. ПРИЧИНА ЗАКРЫТИЯ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS close_reason TEXT; -- "TP", "SL", "manual", "timeout", "market_condition"
ALTER TABLE orders ADD COLUMN IF NOT EXISTS close_trigger TEXT; -- Что именно вызвало закрытие

-- 6. ДОПОЛНИТЕЛЬНЫЕ МЕТРИКИ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS risk_reward_ratio REAL; -- Соотношение риск/прибыль
ALTER TABLE orders ADD COLUMN IF NOT EXISTS position_size_percent REAL; -- Размер позиции от баланса (%)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS slippage_percent REAL; -- Проскальзывание при входе/выходе

-- 7. КОНТЕКСТНАЯ ИНФОРМАЦИЯ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS btc_price_entry REAL; -- Цена BTC на момент входа
ALTER TABLE orders ADD COLUMN IF NOT EXISTS btc_correlation REAL; -- Корреляция с BTC (-1.0 до 1.0)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS session_type TEXT; -- "asian", "european", "american"

-- 8. PUMP/DUMP ДЕТЕКЦИЯ
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pump_dump_detected BOOLEAN; -- Обнаружен ли pump/dump
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pump_dump_type TEXT; -- "pump", "dump", "none"
ALTER TABLE orders ADD COLUMN IF NOT EXISTS unusual_volume BOOLEAN; -- Необычный объем торгов

-- 9. СТРАТЕГИИ ВЫХОДА
ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_strategy_used TEXT; -- Какая стратегия выхода использована
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trailing_stop_used BOOLEAN; -- Использовался ли трейлинг стоп
ALTER TABLE orders ADD COLUMN IF NOT EXISTS partial_close_count INTEGER; -- Количество частичных закрытий

-- 10. МЕТАДАННЫЕ ДЛЯ АНАЛИЗА
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trade_session_id TEXT; -- ID торговой сессии
ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_version TEXT; -- Версия стратегии
ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT; -- Дополнительные заметки

-- Индексы для быстрого поиска и анализа
CREATE INDEX IF NOT EXISTS idx_orders_strategy_combination ON orders(strategy_combination);
CREATE INDEX IF NOT EXISTS idx_orders_market_condition ON orders(market_condition);
CREATE INDEX IF NOT EXISTS idx_orders_close_reason ON orders(close_reason);
CREATE INDEX IF NOT EXISTS idx_orders_signal_strength ON orders(signal_strength);
CREATE INDEX IF NOT EXISTS idx_orders_pnl_percent ON orders(pnl_percent);
CREATE INDEX IF NOT EXISTS idx_orders_buy_time ON orders(buy_time);
CREATE INDEX IF NOT EXISTS idx_orders_user_strategy ON orders(user_id, strategy_combination); 