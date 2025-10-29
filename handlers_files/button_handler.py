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


class ButtonHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def edit_buttons_from_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Edit buttons from the schedule menu using the button management interface"""
        query = update.callback_query
        await query.answer()
        
        # Get current buttons from new_post
        buttons = context.user_data.get("new_post", {}).get("buttons", [])
        
        # Set flag to return to schedule menu after editing
        context.user_data["editing_from_schedule"] = True
        
        # Show button management interface
        keyboard = create_button_management_keyboard(buttons, "new")
        
        await query.message.reply_text(
            f"🔘 *Редагування кнопок*\n\n",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        
        from config import EDIT_BUTTONS_FROM_SCHEDULE
        return EDIT_BUTTONS_FROM_SCHEDULE

    async def add_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        # Show button management interface
        context.user_data["new_post"].setdefault("buttons", [])
        buttons = context.user_data["new_post"]["buttons"]

        keyboard = create_button_management_keyboard(buttons, "new")
        
        # Handle both message and callback query
        if update.message:
            await update.message.reply_text(
                "📋 *Управління кнопками:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "📋 *Управління кнопками:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        return MANAGE_NEW_BUTTONS

    async def skip_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        context.user_data["new_post"]["buttons"] = []
        from handlers_files.schedule_handler import ScheduleHandler
        schedule_handler = ScheduleHandler(self.bot)
        return await schedule_handler.schedule_menu(update, context)

    async def manage_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle button management (add/delete) for new posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        buttons = context.user_data.get("new_post", {}).get("buttons", [])

        if data.startswith("btn_del_new_"):
            # delete button
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(buttons):
                deleted_btn = buttons.pop(idx)
                context.user_data["new_post"]["buttons"] = buttons
                await query.answer(f"Видалено: {deleted_btn['text']}")

            # refresh keyboard
            keyboard = create_button_management_keyboard(buttons, "new")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return MANAGE_NEW_BUTTONS

        elif data == "btn_add_new":
            # prompt to add new button
            await query.message.reply_text(
                "Надішліть кнопку у форматі: `Назва кнопки - https://example.com`",
                parse_mode="Markdown",
            )
            context.user_data["adding_button_to"] = "new_post"
            return MANAGE_NEW_BUTTONS

        elif data == "btn_finish_new":
            # finish and continue to schedule
            await query.message.reply_text("✅ Кнопки налаштовано!")
            
            # Check if we're editing from schedule menu
            if context.user_data.get("editing_from_schedule"):
                # Clear the flag and return to schedule menu
                context.user_data.pop("editing_from_schedule", None)
                from config import SCHEDULE_TIME
                return SCHEDULE_TIME
            else:
                # Normal flow - continue to schedule menu
                from handlers_files.schedule_handler import ScheduleHandler
                schedule_handler = ScheduleHandler(self.bot)
                return await schedule_handler.schedule_menu_from_callback(update, context)

        return MANAGE_NEW_BUTTONS

    async def add_single_button_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Add a single button when in button management mode."""
        adding_to = context.user_data.get("adding_button_to")
        if adding_to != "new_post":
            # Not for new posts, skip this handler
            return None

        try:
            buttons = parse_buttons(update.message.text)
            if buttons:
                current_buttons = context.user_data.get(adding_to, {}).get(
                    "buttons", []
                )
                current_buttons.extend(buttons)
                context.user_data[adding_to]["buttons"] = current_buttons
                await update.message.reply_text("✅ Кнопку додано!")

            context.user_data.pop("adding_button_to", None)

            # show updated keyboard
            keyboard = create_button_management_keyboard(current_buttons, "new")
            await update.message.reply_text(
                "📋 *Управління кнопками:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(
                f"❌ {e}\n\nСпробуйте ще раз у форматі: `Назва - URL`",
                parse_mode="Markdown",
            )

        return MANAGE_NEW_BUTTONS
