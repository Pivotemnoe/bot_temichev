from __future__ import annotations

from app.prompts.triage_clinic_addons import CLINIC_ADDON, CLINIC_POSTOP_ADDON
from app.prompts.triage_plus_expert_addon import PLUS_EXPERT_ADDON


POSTOP_MARKERS = (
    "операция",
    "после операции",
    "послеоперац",
    "шов",
    "швы",
    "снятие швов",
    "наркоз",
    "стерилизац",
    "кастрац",
    "удаление",
    "остеосинтез",
    "пластина",
    "спица",
    "фиксация",
    "перелом",
    "кость",
    "сустав",
)


def is_postop_context(complaint_text: str | None) -> bool:
    text = " ".join(str(complaint_text or "").lower().split())
    if not text:
        return False
    return any(marker in text for marker in POSTOP_MARKERS)


def select_prompt_mode(
    *,
    plan_code: str | None,
    clinic_id: int | None = None,
    complaint_text: str | None = None,
) -> str:
    if clinic_id is not None:
        return "clinic_postop" if is_postop_context(complaint_text) else "clinic"
    if (plan_code or "").strip().lower() == "plus":
        return "plus_expert"
    return "base"


def build_final_system_prompt(
    base_system_prompt: str,
    *,
    plan_code: str | None,
    clinic_id: int | None = None,
    complaint_text: str | None = None,
) -> tuple[str, str]:
    prompt = (base_system_prompt or "").strip()
    mode = select_prompt_mode(
        plan_code=plan_code,
        clinic_id=clinic_id,
        complaint_text=complaint_text,
    )

    addons: list[str] = []
    if mode == "plus_expert":
        addons.append(PLUS_EXPERT_ADDON.strip())
    elif mode in {"clinic", "clinic_postop"}:
        addons.append(CLINIC_ADDON.strip())
        if mode == "clinic_postop":
            addons.append(CLINIC_POSTOP_ADDON.strip())

    final_prompt = "\n\n".join([part for part in [prompt, *addons] if part])
    return final_prompt, mode
