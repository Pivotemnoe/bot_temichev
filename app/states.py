from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_pet_type = State()
    waiting_for_pet_name = State()


class AddPetStates(StatesGroup):
    waiting_for_pet_type = State()
    waiting_for_pet_name = State()


class TriageStates(StatesGroup):
    """
    Состояния для LLM-триажа (разбор жалобы).
    """
    choosing_pet = State()
    asking_age = State()
    asking_duration = State()
    waiting_for_complaint = State()


class ObservationsStates(StatesGroup):
    choosing_pet = State()
