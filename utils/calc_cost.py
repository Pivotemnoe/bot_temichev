# utils/calc_cost.py

PRICES = {
    "4o-mini": {"in": 0.00015, "out": 0.00060},
    "4o":      {"in": 0.00500, "out": 0.01500},
    "4.1":     {"in": 0.01000, "out": 0.03000},
    "5":       {"in": 0.01000, "out": 0.03000},
}

RUB = 93  # курс доллара (можно обновлять ежедневно)


def cost_request(model: str, input_tokens: int, output_tokens: int):
    """Стоимость одного запроса в рублях и долларах."""
    m = PRICES[model]
    usd = (input_tokens / 1000 * m["in"]) + (output_tokens / 1000 * m["out"])
    return usd, usd * RUB


def cost_tariff(model: str, requests: int, input_tokens=350, output_tokens=400):
    """Стоимость тарифа (5 / 10 / 30 запросов)."""
    total = requests * cost_request(model, input_tokens, output_tokens)[1]
    return round(total, 2)


def cost_users(model: str, users: int, avg_requests: int,
               input_tokens=350, output_tokens=400):
    """Стоимость проекта при N пользователях."""
    total = users * avg_requests * cost_request(model, input_tokens, output_tokens)[1]
    return round(total, 2)