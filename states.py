from aiogram.filters.state import State, StatesGroup


class EditDepositPercent(StatesGroup):
    new = State()

class CryptoPairs(StatesGroup):
    pairs = State()

class StatPeriodStates(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()

class SubscriptionStates(StatesGroup):
    waiting_for_pair = State()
    waiting_for_timeframe = State()

class StrategyParamStates(StatesGroup):
    edit_param = State()
    edit_blacklist = State()

class CMParamStates(StatesGroup):
    edit_param = State()

class DivergenceParamStates(StatesGroup):
    edit_param = State()
    edit_stop_loss_type = State()

class RSIParamStates(StatesGroup):
    edit_param = State()

class PumpDumpParamStates(StatesGroup):
    edit_param = State() 