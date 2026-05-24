import json
from datetime import datetime, timezone
from typing import Any


def dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str)


def loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
