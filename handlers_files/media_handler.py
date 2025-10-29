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


class MediaHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def add_media_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle all types of media (photo, video, document)."""
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        # Determine media type and get file_id
        media_type = None
        file_id = None
        
        if update.message.photo:
            media_type = 'photo'
            file_id = update.message.photo[-1].file_id
        elif update.message.video:
            media_type = 'video'
            file_id = update.message.video.file_id
        elif update.message.document:
            # Check if document is an image file
            document = update.message.document
            file_name = document.file_name or ""
            is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'])
            
            if is_image or (document.mime_type and document.mime_type.startswith('image/')):
                # It's an image file - download and re-upload as photo
                try:
                    # Download the file
                    file = await context.bot.get_file(document.file_id)
                    file_path = await file.download_to_drive()
                    
                    # Re-upload as photo to get a photo file_id
                    with open(file_path, 'rb') as photo_file:
                        sent_photo = await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo_file
                        )
                    
                    # Use the photo file_id
                    media_type = 'photo'
                    file_id = sent_photo.photo[-1].file_id
                    
                    # Delete the temporary uploaded photo
                    try:
                        await sent_photo.delete()
                    except:
                        pass
                    
                    # Clean up downloaded file
                    try:
                        import os
                        os.remove(file_path)
                    except:
                        pass
                        
                except Exception as e:
                    # If conversion fails, treat as document
                    await update.message.reply_text(f"⚠️ Не вдалося конвертувати файл у фото. Використовую як документ.")
                    media_type = 'document'
                    file_id = document.file_id
            else:
                # It's a real document (PDF, TXT, DOC, etc.)
                media_type = 'document'
                file_id = document.file_id
        
        if not file_id:
            await update.message.reply_text("❌ Не вдалося обробити медіафайл.")
            return None

        # Store media with type information
        context.user_data["new_post"].setdefault("media", [])
        context.user_data["new_post"]["media"].append({
            'file_id': file_id,
            'type': media_type
        })
        
        media_icon = '🎥' if media_type == 'video' else '📄' if media_type == 'document' else '📷'
        await update.message.reply_text(f"✅ {media_icon} Медіа додано!")
        
        # Show media management interface
        media_list = context.user_data["new_post"]["media"]
        keyboard = create_media_management_keyboard(media_list, "new")
        await update.message.reply_text(
            "📷 *Управління медіа:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        from config import MANAGE_NEW_PHOTOS

        return MANAGE_NEW_PHOTOS

    async def add_photo_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        new_file_id = update.message.photo[-1].file_id
        context.user_data["new_post"].setdefault("photos", [])
        context.user_data["new_post"]["photos"].append(new_file_id)
        await update.message.reply_text(
            "✅ Фото додано! Надішліть ще фото або натисніть 'Завершити вибір фото'.",
            reply_markup=photo_selection_keyboard(),
        )
        from config import ADD_PHOTO

        return ADD_PHOTO

    async def edit_photo_from_schedule(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Edit photos from schedule menu (show management interface)."""
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}
        
        # Set flag to indicate we're editing from schedule menu
        context.user_data["editing_from_schedule"] = True
        
        media_list = context.user_data["new_post"].get("media", [])

        if not media_list:
            await update.callback_query.message.reply_text(
                "📸 *Редагування медіа*\n\n"
                "У цьому пості немає медіа. Надішліть медіа для додавання.",
                parse_mode="Markdown",
            )
        else:
            await update.callback_query.message.reply_text(
                f"📸 *Редагування медіа*\n\n",
                reply_markup=create_media_management_keyboard(media_list, "new"),
                parse_mode="Markdown",
            )
        
        from config import EDIT_PHOTO_FROM_SCHEDULE
        return EDIT_PHOTO_FROM_SCHEDULE

    async def finish_photo_selection_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}
        # ensure media key exists
        context.user_data["new_post"].setdefault("media", [])
        
        # Show media management interface
        media_list = context.user_data["new_post"]["media"]
        keyboard = create_media_management_keyboard(media_list, "new")
        await update.message.reply_text(
            "📷 *Управління медіа:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        from config import MANAGE_NEW_PHOTOS
        return MANAGE_NEW_PHOTOS

    async def skip_photo_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        context.user_data["new_post"]["media"] = []
        
        # Show media management interface
        media_list = context.user_data["new_post"]["media"]
        keyboard = create_media_management_keyboard(media_list, "new")
        await update.message.reply_text(
            "📷 *Управління медіа:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        from config import MANAGE_NEW_PHOTOS
        return MANAGE_NEW_PHOTOS

    async def manage_photos_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle media management for new posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        media_list = context.user_data.get("new_post", {}).get("media", [])
        photos = context.user_data.get("new_post", {}).get("photos", [])

        # Handle new media format
        if data.startswith("media_del_new_"):
            # delete media
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(media_list):
                deleted_media = media_list.pop(idx)
                context.user_data["new_post"]["media"] = media_list
                media_icon = '🎥' if deleted_media['type'] == 'video' else '📄' if deleted_media['type'] == 'document' else '📷'
                await query.answer(f"Видалено {media_icon} {idx + 1}")

            # refresh keyboard
            keyboard = create_media_management_keyboard(media_list, "new")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return MANAGE_NEW_PHOTOS

        elif data == "media_add_new":
            # prompt to add new media
            await query.message.reply_text(
                "📷 Надішліть медіа (фото, відео або файл) для додавання до поста."
            )
            context.user_data["adding_photo_to"] = "new_post"
            return MANAGE_NEW_PHOTOS

        elif data == "media_finish_new":
            # finish and continue to buttons
            await query.message.reply_text("✅ Медіа налаштовано!")
            from handlers_files.button_handler import ButtonHandler
            button_handler = ButtonHandler(self.bot)
            return await button_handler.add_buttons_handler(update, context)

        # Handle old photo format for backward compatibility
        elif data.startswith("photo_del_new_"):
            # delete photo
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(photos):
                deleted_photo = photos.pop(idx)
                context.user_data["new_post"]["photos"] = photos
                await query.answer(f"Видалено фото {idx + 1}")

            # refresh keyboard
            keyboard = create_photo_management_keyboard(photos, "new")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return MANAGE_NEW_PHOTOS

        elif data == "photo_add_new":
            # prompt to add new photo
            await query.message.reply_text(
                "📷 Надішліть фото для додавання до поста."
            )
            context.user_data["adding_photo_to"] = "new_post"
            return MANAGE_NEW_PHOTOS

        elif data == "photo_finish_new":
            # finish and continue to buttons or return to schedule menu
            await query.message.reply_text("✅ Фото налаштовано!")
            
            # Check if we're editing from schedule menu
            if context.user_data.get("editing_from_schedule"):
                # Return to schedule menu
                from handlers_files.preview_handler import PreviewHandler
                preview_handler = PreviewHandler(self.bot)
                await preview_handler.preview_post(update, context, "new_post")
                await query.message.reply_text(
                    "Пост готовий. Надіслати зараз чи запланувати?",
                    reply_markup=create_schedule_keyboard(),
                )
                from config import SCHEDULE_TIME
                return SCHEDULE_TIME
            else:
                # Continue to buttons (normal flow)
                from handlers_files.button_handler import ButtonHandler
                button_handler = ButtonHandler(self.bot)
                return await button_handler.add_buttons_handler(update, context)

        return MANAGE_NEW_PHOTOS

    async def add_single_photo_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Add a single media when in media management mode."""
        adding_to = context.user_data.get("adding_photo_to")
        if adding_to != "new_post":
            # Not for new posts, skip this handler
            return None

        try:
            # Determine media type and get file_id
            media_type = None
            file_id = None
            
            if update.message.photo:
                media_type = 'photo'
                file_id = update.message.photo[-1].file_id
            elif update.message.video:
                media_type = 'video'
                file_id = update.message.video.file_id
            elif update.message.document:
                # Check if document is an image file
                document = update.message.document
                file_name = document.file_name or ""
                is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'])
                
                if is_image or (document.mime_type and document.mime_type.startswith('image/')):
                    # It's an image file - download and re-upload as photo
                    try:
                        # Download the file
                        file = await context.bot.get_file(document.file_id)
                        file_path = await file.download_to_drive()
                        
                        # Re-upload as photo to get a photo file_id
                        with open(file_path, 'rb') as photo_file:
                            sent_photo = await context.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=photo_file
                            )
                        
                        # Use the photo file_id
                        media_type = 'photo'
                        file_id = sent_photo.photo[-1].file_id
                        
                        # Delete the temporary uploaded photo
                        try:
                            await sent_photo.delete()
                        except:
                            pass
                        
                        # Clean up downloaded file
                        try:
                            import os
                            os.remove(file_path)
                        except:
                            pass
                            
                    except Exception as e:
                        # If conversion fails, treat as document
                        await update.message.reply_text(f"⚠️ Не вдалося конвертувати файл у фото. Використовую як документ.")
                        media_type = 'document'
                        file_id = document.file_id
                else:
                    # It's a real document (PDF, TXT, DOC, etc.)
                    media_type = 'document'
                    file_id = document.file_id
            
            if not file_id:
                await update.message.reply_text("❌ Не вдалося обробити медіафайл.")
                return MANAGE_NEW_PHOTOS

            # Store media with type information
            context.user_data["new_post"].setdefault("media", [])
            context.user_data["new_post"]["media"].append({
                'file_id': file_id,
                'type': media_type
            })
            
            media_icon = '🎥' if media_type == 'video' else '📄' if media_type == 'document' else '📷'
            await update.message.reply_text(f"✅ {media_icon} Медіа додано!")

            context.user_data.pop("adding_photo_to", None)

            # show updated keyboard
            media_list = context.user_data["new_post"]["media"]
            keyboard = create_media_management_keyboard(media_list, "new")
            await update.message.reply_text(
                "📷 *Управління медіа:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Помилка при додаванні медіа: {e}"
            )

        return MANAGE_NEW_PHOTOS
