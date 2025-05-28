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
