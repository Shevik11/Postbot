from calendar import monthrange
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _month_year_from(reference_date: datetime, delta_months: int):
    month = (reference_date.month - 1 + delta_months) % 12 + 1
    year = reference_date.year + (reference_date.month - 1 + delta_months) // 12
    return year, month


def create_calendar(reference_date: datetime | None = None) -> InlineKeyboardMarkup:
    """Create an inline keyboard calendar for a given month.
    Returns InlineKeyboardMarkup to be sent as reply_markup.
    Callback data encodes: YYYY-MM-DD for a day, PREV/NEXT/IGNORE for controls.
    """
    ref = reference_date or datetime.now()
    year, month = ref.year, ref.month

    # Header row with month and year (non-clickable)
    month_name = ref.strftime("%B %Y")
    head_row = [InlineKeyboardButton(month_name, callback_data="IGNORE")]

    # Weekday names row (Mon..Sun)
    weekdays = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    weekday_row = [InlineKeyboardButton(d, callback_data="IGNORE") for d in weekdays]

    first_weekday, days_in_month = monthrange(
        year, month
    )  # first_weekday: Mon=0..Sun=6

    # Build day buttons grid
    rows = []
    current_row = []

    # Leading empty days
    for _ in range(first_weekday):
        current_row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        current_row.append(InlineKeyboardButton(str(day), callback_data=date_str))
        if len(current_row) == 7:
            rows.append(current_row)
            current_row = []

    # Trailing empties
    if current_row:
        while len(current_row) < 7:
            current_row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
        rows.append(current_row)

    # Navigation row
    prev_year, prev_month = _month_year_from(ref, -1)
    next_year, next_month = _month_year_from(ref, +1)
    prev_payload = f"PREV:{prev_year:04d}-{prev_month:02d}"
    next_payload = f"NEXT:{next_year:04d}-{next_month:02d}"
    nav_row = [
        InlineKeyboardButton("<", callback_data=prev_payload),
        InlineKeyboardButton(" ", callback_data="IGNORE"),
        InlineKeyboardButton(">", callback_data=next_payload),
    ]

    keyboard = [head_row, weekday_row, *rows, nav_row]
    return InlineKeyboardMarkup(keyboard)


def _build_calendar_for(payload: str) -> InlineKeyboardMarkup:
    """Build calendar for given payload 'YYYY-MM'"""
    year = int(payload[0:4])
    month = int(payload[5:7])
    return create_calendar(datetime(year, month, 1))


def process_calendar_selection(bot, update):
    """Process a callback from the calendar.
    Returns tuple: (is_date_selected, new_keyboard, selected_date)
    - If a day is chosen: (True, None, datetime.date)
    - If navigation/ignore: (False, InlineKeyboardMarkup, None)
    """
    query = update.callback_query
    data = query.data

    # Navigation
    if data.startswith("PREV:") or data.startswith("NEXT:"):
        new_kb = _build_calendar_for(data.split(":", 1)[1])
        return False, new_kb, None

    # Ignore buttons or header/empty cells
    if data == "IGNORE" or data.strip() == "":
        return False, None, None

    # Date selected
    try:
        selected = datetime.strptime(data, "%Y-%m-%d").date()
        return True, None, selected
    except ValueError:
        # Unknown payload, ignore
        return False, None, None
