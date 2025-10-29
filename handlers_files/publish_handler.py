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


class PublishHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    # --- SELECT CHANNEL AND PUBLISH ---
    async def select_channel_menu(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        keyboard = []
        for display_name, channel_id in HARDCODED_CHANNELS.items():
            keyboard.append(
                [
                    InlineKeyboardButton(
                        display_name, callback_data=f"channel_{channel_id}"
                    )
                ]
            )

        await update.effective_message.reply_text(
            "Виберіть канал для публікації:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        from config import SELECT_CHANNEL

        return SELECT_CHANNEL

    async def publish_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        channel_id = query.data.split("_", 1)[1]
        post_data = context.user_data["new_post"]
        publish_time = post_data.get("time")

        if publish_time:
            # scheduled post
            job_id = (
                f"post_{update.effective_user.id}_{int(datetime.now().timestamp())}"
            )
            self.bot.scheduler.add_job(
                self.send_post_job,
                "date",
                run_date=publish_time,
                args=[channel_id, post_data, update.effective_user.id],
                id=job_id,
            )
            # save to db
            # serialize media list for DB storage
            media_list = post_data.get("media", [])
            photos = post_data.get("photos")
            
            # Determine media type and data
            media_to_store = None
            media_type = None
            
            if media_list:
                media_to_store = str(media_list)
                media_type = media_list[0]['type'] if media_list else None
            elif photos:
                media_to_store = str(photos)
                media_type = 'photo'
            elif post_data.get("photo"):
                media_to_store = str([post_data.get("photo")])
                media_type = 'photo'
            
            save_scheduled_post(
                update.effective_user.id,
                post_data.get("text"),
                media_to_store,
                media_type,
                post_data.get("buttons", []),
                publish_time,
                channel_id,
                job_id,
            )
            await query.edit_message_text(
                f"✅ Пост заплановано на {publish_time.strftime('%Y-%m-%d %H:%M')} у канал {channel_id}."
            )
        else:
            # immediate send
            try:
                from handlers_files.preview_handler import PreviewHandler
                preview_handler = PreviewHandler(self.bot)
                await preview_handler.send_post_job(
                    channel_id, post_data, update.effective_user.id, context
                )
                await query.edit_message_text(
                    f"✅ Пост успішно надіслано в канал {channel_id}."
                )
            except Exception as e:
                await query.edit_message_text(
                    f"❌ Не вдалося надіслати пост у канал {channel_id}. Перевірте, чи бот є адміністратором з правами на публікацію."
                )
                return

        context.user_data.clear()
        # send new message with main menu
        welcome_text = "Вітаю! Я допоможу вам керувати публікаціями у вашому каналі."
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=welcome_text,
            reply_markup=create_main_keyboard(),
        )
        from config import MAIN_MENU

        return MAIN_MENU

    async def send_post_job(self, channel_id, post_data, user_id, context=None):
        """function that is called by scheduler to send post."""
        from handlers_files.preview_handler import PreviewHandler
        preview_handler = PreviewHandler(self.bot)
        return await preview_handler.send_post_job(channel_id, post_data, user_id, context)
