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

# Import all handlers from handlers_files
from handlers_files.preview_handler import PreviewHandler
from handlers_files.post_creation_handler import PostCreationHandler
from handlers_files.media_handler import MediaHandler
from handlers_files.button_handler import ButtonHandler
from handlers_files.schedule_handler import ScheduleHandler
from handlers_files.publish_handler import PublishHandler

logger = logging.getLogger(__name__)


class PostHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance

        # Initialize all handler instances
        self.preview_handler = PreviewHandler(bot_instance)
        self.post_creation_handler = PostCreationHandler(bot_instance)
        self.media_handler = MediaHandler(bot_instance)
        self.button_handler = ButtonHandler(bot_instance)
        self.schedule_handler = ScheduleHandler(bot_instance)
        self.publish_handler = PublishHandler(bot_instance)

    # Delegate methods to appropriate handlers
    async def preview_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data_key: str):
        return await self.preview_handler.preview_post(update, context, data_key)

    async def send_post_job(self, channel_id, post_data, user_id, context=None):
        return await self.preview_handler.send_post_job(channel_id, post_data, user_id, context)

    # Post creation methods
    async def create_post_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.post_creation_handler.create_post_start(update, context)

    async def add_text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.post_creation_handler.add_text_handler(update, context)

    async def edit_text_from_schedule_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.post_creation_handler.edit_text_from_schedule_handler(update, context)

    # Media methods
    async def add_media_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.add_media_handler(update, context)

    async def add_photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.add_photo_handler(update, context)

    async def edit_photo_from_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.edit_photo_from_schedule(update, context)

    async def finish_photo_selection_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.finish_photo_selection_handler(update, context)

    async def skip_photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.skip_photo_handler(update, context)

    async def manage_photos_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.manage_photos_handler(update, context)

    async def add_single_photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.media_handler.add_single_photo_handler(update, context)

    # Button methods
    async def edit_buttons_from_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.button_handler.edit_buttons_from_schedule(update, context)

    async def add_buttons_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.button_handler.add_buttons_handler(update, context)

    async def skip_buttons_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.button_handler.skip_buttons_handler(update, context)

    async def manage_buttons_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.button_handler.manage_buttons_handler(update, context)

    async def add_single_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.button_handler.add_single_button_handler(update, context)

    # Schedule methods
    async def schedule_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.schedule_handler.schedule_menu(update, context)

    async def schedule_time_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.schedule_handler.schedule_time_handler(update, context)

    async def set_schedule_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.schedule_handler.set_schedule_time(update, context)

    async def calendar_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.schedule_handler.calendar_callback_handler(update, context)

    async def schedule_menu_from_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.schedule_handler.schedule_menu_from_callback(update, context)

    # Publish methods
    async def select_channel_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.publish_handler.select_channel_menu(update, context)

    async def perform_publish(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.publish_handler.publish_handler(update, context)