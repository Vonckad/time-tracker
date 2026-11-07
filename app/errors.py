"""Human-readable Russian error messages for the API."""

from __future__ import annotations

from typing import Any, Iterable

FIELD_NAMES = {
    "name": "Имя",
    "title": "Должность",
    "description": "Описание задачи",
    "employee_id": "Сотрудник",
    "start": "Начало",
    "end": "Конец",
    "from": "Дата «С»",
    "to": "Дата «По»",
    "page": "Страница",
    "per_page": "Размер страницы",
    "to_index": "Позиция",
    "with_history": "Режим удаления",
    "include_deleted": "Показывать удалённых",
}

HTTP_DEFAULTS = {
    400: "Некорректный запрос",
    404: "Не найдено",
    405: "Метод не поддерживается",
    422: "Проверьте введённые данные",
    500: "Внутренняя ошибка сервера",
}


def _field(loc: Iterable[Any]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    if not parts:
        return "Данные запроса"
    return FIELD_NAMES.get(parts[-1], parts[-1])


def _one(err: dict) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    field = _field(err.get("loc", ()))
    if kind == "missing":
        return f"Поле «{field}» обязательно"
    if kind == "string_too_short":
        if ctx.get("min_length", 1) <= 1:
            return f"Поле «{field}» не может быть пустым"
        return f"Поле «{field}»: минимум {ctx['min_length']} символов"
    if kind == "string_too_long":
        return f"Поле «{field}»: максимум {ctx.get('max_length')} символов"
    if kind.startswith("int") or kind.startswith("float"):
        return f"Поле «{field}» должно быть числом"
    if kind.startswith("bool"):
        return f"Поле «{field}» должно быть да/нет"
    if kind.startswith("string"):
        return f"Поле «{field}» должно быть текстом"
    if kind in ("greater_than_equal", "greater_than"):
        return f"Поле «{field}» должно быть не меньше {ctx.get('ge', ctx.get('gt'))}"
    if kind in ("less_than_equal", "less_than"):
        return f"Поле «{field}» должно быть не больше {ctx.get('le', ctx.get('lt'))}"
    if kind in ("json_invalid", "model_attributes_type", "dict_type"):
        return "Некорректный формат запроса"
    return f"Некорректное значение поля «{field}»"


def validation_message(errors: list[dict]) -> str:
    seen: list[str] = []
    for err in errors:
        msg = _one(err)
        if msg not in seen:
            seen.append(msg)
    return "; ".join(seen) or HTTP_DEFAULTS[422]


def http_message(status: int, detail: Any) -> str:
    if isinstance(detail, str) and detail and not detail.isascii():
        return detail  # already a Russian message from the app
    return HTTP_DEFAULTS.get(status, "Ошибка запроса")
