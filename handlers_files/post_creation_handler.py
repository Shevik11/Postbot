import logging
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import CallbackQueryHandler, ContextTypes

from config import HARDCODED_CHANNELS, MANAGE_NEW_BUTTONS, MANAGE_NEW_PHOTOS, EDIT_BUTTONS_FROM_SCHEDULE
from database import (
    delete_scheduled_post,
    get_job_id_by_post_id,
    get_scheduled_post_by_id,
    get_scheduled_posts,
    save_published_post,
    save_scheduled_post,
    update_scheduled_post,
)
from telegramcalendar import create_calendar, process_calendar_selection
from utils import (
    cancel_keyboard,
    clean_unsupported_formatting,
    create_button_management_keyboard,
    create_buttons_markup,
    create_edit_menu_keyboard,
    create_main_keyboard,
    create_media_management_keyboard,
    create_photo_management_keyboard,
    photo_selection_keyboard,
    create_schedule_keyboard,
    detect_parse_mode,
    entities_to_html,
    format_text_for_preview,
    get_formatting_warnings,
    parse_buttons,
    photo_selection_keyboard,
    skip_keyboard,
    skip_photo_keyboard,
)

logger = logging.getLogger(__name__)


class PostCreationHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    # --- CREATE POST ---
    async def create_post_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        context.user_data["new_post"] = {}
        await update.message.reply_text(
            "Крок 1: Надішліть текст для вашого поста.", reply_markup=cancel_keyboard()
        )
        from config import ADD_TEXT

        return ADD_TEXT

    async def add_text_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        text = update.message.text

        # Convert entities to HTML tags to preserve formatting
        if update.message.entities:
            text = entities_to_html(text, update.message.entities)

        context.user_data["new_post"]["text"] = text

        # Go directly to media management interface
        context.user_data["new_post"].setdefault("media", [])
        media_list = context.user_data["new_post"]["media"]
        keyboard = create_media_management_keyboard(media_list, "new")
        await update.message.reply_text(
            "📷 *Управління медіа:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        from config import MANAGE_NEW_PHOTOS

        return MANAGE_NEW_PHOTOS

    async def edit_text_from_schedule_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle text editing from schedule menu."""
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        text = update.message.text

        # Convert entities to HTML tags to preserve formatting
        if update.message.entities:
            text = entities_to_html(text, update.message.entities)

        context.user_data["new_post"]["text"] = text

        # Return to schedule menu
        from handlers_files.preview_handler import PreviewHandler
        preview_handler = PreviewHandler(self.bot)
        await preview_handler.preview_post(update, context, "new_post")
        await update.message.reply_text(
            "Пост готовий. Надіслати зараз чи запланувати?",
            reply_markup=create_schedule_keyboard(),
        )
        from config import SCHEDULE_TIME
        return SCHEDULE_TIME
