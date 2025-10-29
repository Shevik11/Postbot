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
    ADD_TEXT,
    DELETE_PUBLISHED_CONFIRM,
    EDIT_PUBLISHED_MENU,
    EDIT_PUBLISHED_TEXT,
    EDIT_SCHEDULED_POST,
    EDIT_SCHEDULED_TEXT,
    EDIT_SCHEDULED_PHOTO,
    EDIT_SCHEDULED_BUTTONS,
    EDIT_SCHEDULED_TIME,
    MAIN_MENU,
    MANAGE_NEW_BUTTONS,
    MANAGE_NEW_PHOTOS,
    EDIT_PUBLISHED_POST,
    SCHEDULE_TIME,
    SELECT_CHANNEL,
    VIEW_PUBLISHED_POSTS,
    VIEW_SCHEDULED,
    ADD_PHOTO,
    EDIT_TEXT_FROM_SCHEDULE,
    EDIT_BUTTONS_FROM_SCHEDULE,
    EDIT_PHOTO_FROM_SCHEDULE,
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.main_menu_handler),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            ],
            # create post
            ADD_TEXT: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.post_handlers.add_text_handler
                ),
            ],
            ADD_BUTTONS: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
                MessageHandler(
                    filters.Regex(r"Пропустити"), bot.post_handlers.skip_buttons_handler
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.post_handlers.add_buttons_handler,
                ),
            ],
            # manage photos for NEW posts
            MANAGE_NEW_PHOTOS: [
                CallbackQueryHandler(
                    bot.post_handlers.manage_photos_handler,
                    pattern=r"^(media_|photo_)(del_new_\d+|add_new|finish_new)$",
                ),
                MessageHandler(
                    filters.PHOTO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.VIDEO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.Document.ALL,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # add photos for NEW posts
            ADD_PHOTO: [
                MessageHandler(
                    filters.PHOTO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.VIDEO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.Document.ALL,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit text from schedule menu
            EDIT_TEXT_FROM_SCHEDULE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.post_handlers.edit_text_from_schedule_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit photos from schedule menu
            EDIT_PHOTO_FROM_SCHEDULE: [
                CallbackQueryHandler(
                    bot.post_handlers.manage_photos_handler,
                    pattern=r"^photo_(del_new_\d+|add_new|finish_new)$",
                ),
                MessageHandler(
                    filters.PHOTO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.VIDEO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.Document.ALL,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit buttons from schedule menu
            EDIT_BUTTONS_FROM_SCHEDULE: [
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
            # schedule post
            SCHEDULE_TIME: [
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                CallbackQueryHandler(
                    bot.post_handlers.schedule_time_handler,
                    pattern=r"^(send_now|schedule|edit_text|edit_photo|edit_buttons|layout_photo_bottom)$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.change_layout_handler,
                    pattern="^change_layout$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.handle_layout_choice,
                    pattern=r"^(layout_photo_top|layout_photo_bottom|back_to_schedule)$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.manage_photos_handler,
                    pattern=r"^photo_(del_new_\d+|add_new|finish_new)$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.manage_buttons_handler,
                    pattern=r"^btn_(del_new_\d+|add_new|finish_new)$",
                ),
                CallbackQueryHandler(
                    bot.post_handlers.calendar_callback_handler,
                    pattern=r"^(?:\d{4}-\d{2}-\d{2}|(?:PREV|NEXT):\d{4}-\d{2}|IGNORE)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.post_handlers.set_schedule_time
                ),
                MessageHandler(
                    filters.PHOTO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.VIDEO,
                    bot.post_handlers.add_media_handler,
                ),
                MessageHandler(
                    filters.Document.ALL,
                    bot.post_handlers.add_media_handler,
                ),
            ],
            SELECT_CHANNEL: [
                CallbackQueryHandler(
                    bot.post_handlers.perform_publish, pattern="^channel_"
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
                    pattern="^(edit_text|edit_photo|edit_buttons|edit_layout|edit_time|preview_edit|save_edit|cancel_edit)$",
                ),
                CallbackQueryHandler(
                    bot.scheduled_handlers.handle_scheduled_layout_choice,
                    pattern=r"^(layout_photo_top|layout_photo_bottom|back_to_schedule)$",
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
            # edit scheduled post photos
            EDIT_SCHEDULED_PHOTO: [
                CallbackQueryHandler(
                    bot.scheduled_handlers.manage_scheduled_photos_handler,
                    pattern=r"^photo_(del_scheduled_\d+|add_scheduled|finish_scheduled)$",
                ),
                MessageHandler(
                    filters.PHOTO,
                    bot.scheduled_handlers.add_photo_to_edit,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit scheduled post buttons
            EDIT_SCHEDULED_BUTTONS: [
                CallbackQueryHandler(
                    bot.scheduled_handlers.manage_scheduled_buttons_handler,
                    pattern=r"^btn_(del_scheduled_\d+|add_scheduled|finish_scheduled)$",
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.scheduled_handlers.add_button_to_edit,
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            ],
            # edit already published posts
            EDIT_PUBLISHED_MENU: [
                CallbackQueryHandler(
                    bot.edit_delete_published_handler,
                    pattern=r"^(ep_edit_text|ep_edit_buttons|ep_back_to_list|ep_cancel)$",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            ],
            EDIT_PUBLISHED_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, bot.edit_published_text
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            ],
            # delete published posts confirmation
            DELETE_PUBLISHED_CONFIRM: [
                CallbackQueryHandler(
                    bot.delete_published_confirm_handler,
                    pattern=r"^(dp_confirm_|dp_cancel)",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            ],
            # edit published post interface
            EDIT_PUBLISHED_POST: [
                CallbackQueryHandler(
                    bot.edit_delete_published_handler,
                    pattern=r"^ep_(edit_text|edit_photos|edit_buttons|save_changes|cancel)$",
                ),
                MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
                MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            ],
            # view published posts
            VIEW_PUBLISHED_POSTS: [
                CallbackQueryHandler(
                    bot.preview_published_post,
                    pattern=r"^preview_",
                ),
                CallbackQueryHandler(
                    bot.back_to_posts_list,
                    pattern=r"^back_to_posts$",
                ),
                CallbackQueryHandler(
                    bot.edit_delete_published_handler,
                    pattern=r"^(editpublished_|deletepublished_)",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.main_menu_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", bot.cancel),
            MessageHandler(filters.Regex("^❌ Скасувати$"), bot.cancel),
            MessageHandler(filters.Regex("^(Створити пост|Відкладені пости|Існуючі пости)$"), bot.main_menu_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, bot.main_menu_handler),
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
