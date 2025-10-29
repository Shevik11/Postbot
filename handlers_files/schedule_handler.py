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


class ScheduleHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    # --- PREVIEW AND SCHEDULE ---
    async def schedule_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from handlers_files.preview_handler import PreviewHandler
        preview_handler = PreviewHandler(self.bot)
        await preview_handler.preview_post(update, context, "new_post")
        await update.message.reply_text(
            "Пост готовий. Надіслати зараз чи запланувати?",
            reply_markup=create_schedule_keyboard(),
        )
        from config import SCHEDULE_TIME

        return SCHEDULE_TIME

    async def schedule_time_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()
        
        if query.data == "send_now":
            from handlers_files.publish_handler import PublishHandler
            publish_handler = PublishHandler(self.bot)
            return await publish_handler.select_channel_menu(update, context)
        elif query.data == "schedule":
            cal = create_calendar()
            await query.message.reply_text("Оберіть дату публікації:", reply_markup=cal)
            from config import SCHEDULE_TIME

            return SCHEDULE_TIME
        elif query.data == "edit_text":
            await query.message.reply_text("✏️ Надішліть новий текст:")
            from config import EDIT_TEXT_FROM_SCHEDULE
            return EDIT_TEXT_FROM_SCHEDULE
        elif query.data == "edit_photo":
            from handlers_files.media_handler import MediaHandler
            media_handler = MediaHandler(self.bot)
            return await media_handler.edit_photo_from_schedule(update, context)
        elif query.data == "edit_buttons":
            from handlers_files.button_handler import ButtonHandler
            button_handler = ButtonHandler(self.bot)
            return await button_handler.edit_buttons_from_schedule(update, context)
        elif query.data == "layout_photo_bottom":
            context.user_data.setdefault("new_post", {})
            context.user_data["new_post"]["layout"] = "photo_bottom"
            await query.answer("Розкладка: фото під текстом")
            # Refresh preview and show menu again
            from handlers_files.preview_handler import PreviewHandler
            preview_handler = PreviewHandler(self.bot)
            await preview_handler.preview_post(update, context, "new_post")
            await query.message.reply_text(
                "Пост готовий. Надіслати зараз чи запланувати?",
                reply_markup=create_schedule_keyboard(),
            )
            from config import SCHEDULE_TIME
            return SCHEDULE_TIME

    async def set_schedule_time(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        # This handler now expects time (HH:MM) after date chosen via calendar
        try:
            date_obj = context.user_data.get("selected_date")
            if not date_obj:
                await update.message.reply_text("Спочатку оберіть дату у календарі.")
                from config import SCHEDULE_TIME

                return SCHEDULE_TIME
            time_obj = datetime.strptime(update.message.text, "%H:%M").time()
            publish_time = datetime.combine(date_obj, time_obj)
            if publish_time < datetime.now():
                await update.message.reply_text(
                    "Цей час вже минув. Введіть майбутню дату/час."
                )
                from config import SCHEDULE_TIME

                return SCHEDULE_TIME
            context.user_data["new_post"]["time"] = publish_time
            context.user_data.pop("selected_date", None)
            from handlers_files.publish_handler import PublishHandler
            publish_handler = PublishHandler(self.bot)
            return await publish_handler.select_channel_menu(update, context)
        except ValueError:
            await update.message.reply_text(
                "Невірний формат часу. Надішліть у форматі ГГ:ХХ, напр. 23:59"
            )
            from config import SCHEDULE_TIME

            return SCHEDULE_TIME

    async def calendar_callback_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()
        result, key, date = process_calendar_selection(context.bot, update)
        if result and date:
            context.user_data["selected_date"] = date
            await query.message.reply_text(
                "Оберіть час у форматі ГГ:ХХ (наприклад 23:59)"
            )
        else:
            # refresh calendar keyboard
            await query.edit_message_reply_markup(reply_markup=key)
        from config import SCHEDULE_TIME

        return SCHEDULE_TIME

    async def schedule_menu_from_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show schedule menu after callback (not from message)."""
        from handlers_files.preview_handler import PreviewHandler
        preview_handler = PreviewHandler(self.bot)
        await preview_handler.preview_post(update, context, "new_post")

        await update.callback_query.message.reply_text(
            "Пост готовий. Надіслати зараз чи запланувати?",
            reply_markup=create_schedule_keyboard(),
        )
        from config import SCHEDULE_TIME

        return SCHEDULE_TIME
