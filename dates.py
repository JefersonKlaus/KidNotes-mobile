"""Date helpers shared by the UI (birth dates and ages)."""

from datetime import date, datetime


def to_local_date(value: date | datetime | str | None) -> date | None:
    """Convert a value coming from the date picker into a calendar date.

    The picker may send a timezone-aware datetime (UTC). Converting it to the
    device's local time before taking the date avoids off-by-one-day errors.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return (value.astimezone() if value.tzinfo else value).date()
    return value


def age_in_months(birth_date: date, today: date | None = None) -> int:
    """Whole months between `birth_date` and `today` (never negative)."""
    today = today or date.today()
    months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    if today.day < birth_date.day:
        months -= 1
    return max(months, 0)
