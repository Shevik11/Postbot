import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def detect_parse_mode(text: str):
    """Return appropriate Telegram parse_mode for given text or None.

    Heuristics:
    - If HTML-like tags are present (e.g., <b>, <i>, <u>, <s>, <a href=...>), use 'HTML'.
    - Else if common Markdown markers are present (e.g., *bold*, _italic_, [text](url), `code`), use 'Markdown'.
    - Else return None (plain text).

    Supported HTML tags: <b>, <strong>, <i>, <em>, <u>, <s>, <strike>, <code>, <pre>, <a href="">, <blockquote>, <tg-spoiler>.
    """
    if not text:
        return None

    sample = text.strip()

    # Simple HTML detection
    if (
        "<b>" in sample
        or "</b>" in sample
        or "<strong>" in sample
        or "</strong>" in sample
        or "<i>" in sample
        or "</i>" in sample
        or "<em>" in sample
        or "</em>" in sample
        or "<u>" in sample
        or "</u>" in sample
        or "<s>" in sample
        or "</s>" in sample
        or "<strike>" in sample
        or "</strike>" in sample
        or "<a href=" in sample
        or "</a>" in sample
        or "<code>" in sample
        or "</code>" in sample
        or "<pre>" in sample
        or "</pre>" in sample
        or "<tg-spoiler>" in sample
        or "</tg-spoiler>" in sample
        or "<blockquote>" in sample
        or "</blockquote>" in sample
    ):
        return "HTML"

    # Basic Markdown detection
    if (
        "**" in sample  # bold (some users enter double asterisks)
        or "*" in sample  # bold/italic legacy
        or "_" in sample  # italic/underline legacy
        or "[`".strip() in sample
        or "`" in sample  # inline code/backticks
        or "](" in sample  # [text](url)
        or sample.startswith("#")  # headings pasted as markdown
    ):
        return "Markdown"

    return None


def entities_to_html(text: str, entities):
    """Convert Telegram entities to HTML tags."""
    if not text or not entities:
        return text

    # Sort entities by offset in reverse order to avoid position shifts
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)

    result = text
    for entity in sorted_entities:
        start = entity.offset
        end = entity.offset + entity.length
        entity_text = text[start:end]

        # Map entity types to HTML tags (supported by Telegram Bot API)
        if entity.type == "bold":
            replacement = f"<b>{entity_text}</b>"
        elif entity.type == "italic":
            replacement = f"<i>{entity_text}</i>"
        elif entity.type == "underline":
            replacement = f"<u>{entity_text}</u>"
        elif entity.type == "strikethrough":
            replacement = f"<s>{entity_text}</s>"
        elif entity.type == "spoiler":
            replacement = f"<tg-spoiler>{entity_text}</tg-spoiler>"
        elif entity.type == "blockquote":
            replacement = f"<blockquote>{entity_text}</blockquote>"
        elif entity.type == "code":
            replacement = f"<code>{entity_text}</code>"
        elif entity.type == "pre":
            # Check if language is specified
            if hasattr(entity, "language") and entity.language:
                replacement = f'<pre><code class="language-{entity.language}">{entity_text}</code></pre>'
            else:
                replacement = f"<pre>{entity_text}</pre>"
        elif entity.type == "text_link":
            url = entity.url if hasattr(entity, "url") else ""
            replacement = f'<a href="{url}">{entity_text}</a>'
        elif entity.type == "text_mention":
            # Text mention (@username) - keep as plain text
            replacement = entity_text
        elif entity.type == "url":
            # Plain URL in text - keep as is (Telegram auto-links it)
            replacement = entity_text
        elif entity.type == "email":
            # Email address - keep as is
            replacement = entity_text
        elif entity.type == "phone_number":
            # Phone number - keep as is
            replacement = entity_text
        elif entity.type == "mention":
            # @username - keep as is
            replacement = entity_text
        elif entity.type == "hashtag":
            # #hashtag - keep as is
            replacement = entity_text
        elif entity.type == "cashtag":
            # $TICKER - keep as is
            replacement = entity_text
        elif entity.type == "bot_command":
            # /command - keep as is
            replacement = entity_text
        else:
            # Unknown type, keep as plain text
            replacement = entity_text

        result = result[:start] + replacement + result[end:]

    return result


def clean_unsupported_formatting(text: str):
    """Clean text for Telegram (currently all basic HTML tags are supported)."""
    # All basic HTML tags (<b>, <i>, <u>, <s>, <code>, <pre>, <a>) are supported by Bot API
    # Just return text as-is
    return text


def format_text_for_preview(text: str):
    """Format text to show what will actually be sent to Telegram."""
    if not text:
        return text

    # Clean unsupported formatting
    clean_text = clean_unsupported_formatting(text)

    return clean_text


def get_formatting_warnings(text: str):
    """Get warnings about unsupported formatting."""
    # All basic HTML tags are now supported by Bot API
    # Return empty list
    return []


def cancel_keyboard():
    """create keyboard with cancel button."""
    return ReplyKeyboardMarkup([["❌ Скасувати"]], resize_keyboard=True)


def skip_keyboard():
    """create keyboard with skip and cancel buttons."""
    return ReplyKeyboardMarkup(
        [["➡️ Пропустити"], ["❌ Скасувати"]], resize_keyboard=True
    )


def skip_photo_keyboard():
    """create keyboard with skip photo and cancel buttons."""
    return ReplyKeyboardMarkup(
        [["➡️ Пропустити фото"], ["❌ Скасувати"]], resize_keyboard=True
    )


def photo_selection_keyboard():
    """create keyboard for adding multiple photos or skipping."""
    return ReplyKeyboardMarkup(
        [["✅ Завершити вибір фото"], ["➡️ Пропустити фото"], ["❌ Скасувати"]],
        resize_keyboard=True,
    )


def photo_management_keyboard(photos):
    """create keyboard for managing photos (add/delete/view)."""
    keyboard = []

    # Show existing photos with delete option
    if photos:
        for idx, photo_id in enumerate(photos):
            keyboard.append([f"❌ Видалити фото {idx + 1}"])

        # Add option to delete all photos
        if len(photos) > 1:
            keyboard.append(["🗑️ Видалити всі фото"])

    # Add new photo and finish options
    keyboard.append(["➕ Додати нове фото"])
    if photos:
        keyboard.append(["👀 Попередній перегляд фото"])
    keyboard.append(["✅ Завершити редагування фото"])
    keyboard.append(["❌ Скасувати"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def parse_buttons(buttons_text):
    """parse buttons text in format 'Name - URL'."""
    buttons = []
    try:
        for line in buttons_text.split("\n"):
            if "-" in line:
                text, url = line.split("-", 1)
                buttons.append({"text": text.strip(), "url": url.strip()})
        return buttons
    except Exception as e:
        logger.error(f"Error parsing buttons: {e}")
        raise ValueError(f"Error parsing buttons: {e}")


def create_buttons_markup(buttons):
    """create InlineKeyboardMarkup with buttons."""
    if not buttons:
        return None

    try:
        keyboard = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
        result = InlineKeyboardMarkup(keyboard)
        return result
    except Exception as e:
        logger.error(f"Error creating buttons markup: {e}")
        return None


def create_main_keyboard():
    """create main keyboard for bot."""
    from telegram import KeyboardButton

    keyboard = [
        [KeyboardButton("📝 Створити пост")],
        [KeyboardButton("📅 Відкладені пости")],
        [KeyboardButton("📋 Існуючі пости")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_edit_menu_keyboard():
    """create edit menu keyboard for post."""
    keyboard = [
        [InlineKeyboardButton("✏️ Редагувати текст", callback_data="edit_text")],
        [InlineKeyboardButton("📷 Редагувати фото", callback_data="edit_photo")],
        [InlineKeyboardButton("🔘 Редагувати кнопки", callback_data="edit_buttons")],
        [InlineKeyboardButton("✏️ Змінити час", callback_data="edit_time")],
        [InlineKeyboardButton("👀 Попередній перегляд", callback_data="preview_edit")],
        [InlineKeyboardButton("✅ Зберегти зміни", callback_data="save_edit")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="cancel_edit")],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_schedule_keyboard():
    """create schedule keyboard for post."""
    keyboard = [
        [InlineKeyboardButton("✅ Надіслати зараз", callback_data="send_now")],
        [InlineKeyboardButton("🕓 Відкласти публікацію", callback_data="schedule")],
        [InlineKeyboardButton("✏️ Редагувати текст", callback_data="edit_text")],
        [InlineKeyboardButton("📷 Редагувати фото", callback_data="edit_photo")],
        [InlineKeyboardButton("🔘 Редагувати кнопки", callback_data="edit_buttons")],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_button_management_keyboard(buttons, context="new"):
    """create keyboard for managing buttons (add/delete)."""
    keyboard = []

    # show existing buttons with delete option
    for idx, btn in enumerate(buttons):
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"❌ {btn['text']}", callback_data=f"btn_del_{context}_{idx}"
                )
            ]
        )

    # add new button and finish options
    keyboard.append(
        [InlineKeyboardButton("➕ Додати кнопку", callback_data=f"btn_add_{context}")]
    )
    keyboard.append(
        [InlineKeyboardButton("✅ Завершити", callback_data=f"btn_finish_{context}")]
    )

    return InlineKeyboardMarkup(keyboard)


def create_photo_management_keyboard(photos, context="new"):
    """create keyboard for managing photos (add/delete)."""
    keyboard = []

    # show existing photos with delete option
    for idx, photo in enumerate(photos):
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"❌ Фото {idx + 1}", callback_data=f"photo_del_{context}_{idx}"
                )
            ]
        )

    # add new photo and finish options
    keyboard.append(
        [InlineKeyboardButton("➕ Додати фото", callback_data=f"photo_add_{context}")]
    )
    keyboard.append(
        [InlineKeyboardButton("✅ Завершити", callback_data=f"photo_finish_{context}")]
    )

    return InlineKeyboardMarkup(keyboard)
