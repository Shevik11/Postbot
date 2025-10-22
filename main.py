import asyncio
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot import ChannelBot
from config import (
    ADD_BUTTONS,
    ADD_PHOTO,
    ADD_TEXT,
    DELETE_PUBLISHED_CONFIRM,
    EDIT_PUBLISHED_BUTTONS,
    EDIT_PUBLISHED_MENU,
    EDIT_PUBLISHED_TEXT,
    EDIT_SCHEDULED_BUTTONS,
    EDIT_SCHEDULED_PHOTO,
    EDIT_SCHEDULED_POST,
    EDIT_SCHEDULED_TEXT,
    EDIT_SCHEDULED_TIME,
    MAIN_MENU,
    MANAGE_EDIT_BUTTONS,
    MANAGE_NEW_BUTTONS,
    MANAGE_PUBLISHED_BUTTONS,
    SCHEDULE_TIME,
    SELECT_CHANNEL,
    VIEW_SCHEDULED,
    get_bot_token,
)
from database import db_connect


async def main():
    # Create database on startup
    db_connect()

    TOKEN = get_bot_token()
    if not TOKEN:
        print("No BOT_TOKEN")
        return

    # Create scheduler
    scheduler = AsyncIOScheduler()
    scheduler.start()

    # create bot instance
    bot = ChannelBot(scheduler)
    application = Application.builder().token(TOKEN).build()

    # configure ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.main_menu_handler)
            ],
            # create post
            ADD_TEXT: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.post_handlers.add_text_handler
                ),
            ],
            ADD_PHOTO: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.PHOTO, bot.post_handlers.add_photo_handler),
                MessageHandler(
                    filters.Regex(r"^✅ Завершити вибір фото$"),
                    bot.post_handlers.finish_photo_selection_handler,
                ),
                MessageHandler(
                    filters.Regex(r"^➡️ Пропустити фото$"),
                    bot.post_handlers.skip_photo_handler,
                ),
            ],
            ADD_BUTTONS: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(
                    filters.Regex(r"Пропустити"), bot.post_handlers.skip_buttons_handler
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.post_handlers.add_buttons_handler,
                ),
            ],
            # manage buttons for NEW posts
            MANAGE_NEW_BUTTONS: [
                CallbackQueryHandler(
                    bot.post_handlers.manage_buttons_handler,
                    pattern=r"^btn_(del_new_\d+|add_new|finish_new)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.post_handlers.add_single_button_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # manage buttons for EDITING scheduled posts
            MANAGE_EDIT_BUTTONS: [
                CallbackQueryHandler(
                    bot.scheduled_handlers.manage_edit_buttons_handler,
                    pattern=r"^btn_(del_edit_\d+|add_edit|finish_edit)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.scheduled_handlers.add_single_button_to_edit_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # manage buttons for PUBLISHED posts
            MANAGE_PUBLISHED_BUTTONS: [
                CallbackQueryHandler(
                    bot.manage_published_buttons_handler,
                    pattern=r"^btn_(del_published_\d+|add_published|finish_published)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.add_single_button_to_published_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # schedule post
            SCHEDULE_TIME: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                CallbackQueryHandler(
                    bot.post_handlers.schedule_time_handler,
                    pattern=r"^(send_now|schedule)$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.calendar_callback_handler,
                    pattern=r"^(?:\d{4}-\d{2}-\d{2}|(?:PREV|NEXT):\d{4}-\d{2}|IGNORE)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.post_handlers.set_schedule_time
                ),
            ],
            SELECT_CHANNEL: [
                CallbackQueryHandler(
                    bot.post_handlers.publish_handler, pattern="^channel_"
                )
            ],
            # view scheduled posts
            VIEW_SCHEDULED: [
                CallbackQueryHandler(
                    bot.scheduled_handlers.cancel_scheduled_post,
                    pattern="^cancel_scheduled_",
                ),
                CallbackQueryHandler(
                    bot.scheduled_handlers.edit_scheduled_post_start,
                    pattern="^edit_scheduled_",
                ),
                CallbackQueryHandler(
                    bot.scheduled_handlers.publish_now_scheduled_post,
                    pattern="^publish_now_",
                ),
            ],
            # edit scheduled posts
            EDIT_SCHEDULED_POST: [
                CallbackQueryHandler(
                    bot.scheduled_handlers.edit_post_menu_handler,
                    pattern="^(edit_text|edit_photo|edit_buttons|edit_time|preview_edit|save_edit|cancel_edit)$",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_SCHEDULED_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.scheduled_handlers.edit_scheduled_time,
                ),
                CallbackQueryHandler(
                    bot.scheduled_handlers.edit_calendar_callback_handler,
                    pattern=r"^(?:\d{4}-\d{2}-\d{2}|(?:PREV|NEXT):\d{4}-\d{2}|IGNORE)$",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_SCHEDULED_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.scheduled_handlers.edit_scheduled_text,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_SCHEDULED_PHOTO: [
                MessageHandler(filters.PHOTO, bot.scheduled_handlers.add_photo_to_edit),
                MessageHandler(
                    filters.Regex(r"^❌ Видалити фото \d+$"),
                    bot.scheduled_handlers.delete_photo_from_edit,
                ),
                MessageHandler(
                    filters.Regex(r"^🗑️ Видалити всі фото$"),
                    bot.scheduled_handlers.delete_all_photos_edit,
                ),
                MessageHandler(
                    filters.Regex(r"^➕ Додати нове фото$"),
                    bot.scheduled_handlers.prompt_add_photo,
                ),
                MessageHandler(
                    filters.Regex(r"^👀 Попередній перегляд фото$"),
                    bot.scheduled_handlers.preview_edit_photos,
                ),
                MessageHandler(
                    filters.Regex(r"^✅ Завершити редагування фото$"),
                    bot.scheduled_handlers.finish_edit_photo_selection_handler,
                ),
                MessageHandler(
                    filters.Regex(r"^✅ Завершити вибір фото$"),
                    bot.scheduled_handlers.finish_edit_photo_selection_handler,
                ),
                MessageHandler(
                    filters.Regex(r"^➡️ Пропустити фото$"),
                    bot.scheduled_handlers.skip_photo_edit,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_SCHEDULED_BUTTONS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.scheduled_handlers.edit_scheduled_buttons,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit already published posts
            EDIT_PUBLISHED_MENU: [
                CallbackQueryHandler(
                    bot.edit_published_menu_handler,
                    pattern=r"^(ep_edit_text|ep_edit_buttons|ep_cancel)$",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_PUBLISHED_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.edit_published_text
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            EDIT_PUBLISHED_BUTTONS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.edit_published_buttons
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # delete published posts confirmation
            DELETE_PUBLISHED_CONFIRM: [
                CallbackQueryHandler(
                    bot.delete_published_confirm_handler,
                    pattern=r"^(dp_confirm_|dp_cancel)",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", bot.cancel),
            MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
        ],
        allow_reentry=True,
    )

    # add handlers
    application.add_handler(conv_handler)
    application.add_handler(
        CallbackQueryHandler(
            bot.edit_delete_published_handler,
            pattern="^(editpublished|deletepublished)_",
        )
    )

    print("Bot started!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nBot stop")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
