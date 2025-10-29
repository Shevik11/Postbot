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
    upload_photo_to_telegraph_by_file_id,
)

logger = logging.getLogger(__name__)


class PreviewHandler:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def preview_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data_key: str
    ):
        """show preview of post."""
        post_data = context.user_data.get(data_key, {})
        text = post_data.get("text", "Немає тексту")
        
        # Check for new media format first
        media_list = post_data.get("media", [])
        photos = post_data.get("photos")
        
        # Fallback to old photos format
        if not media_list and not photos and post_data.get("photo"):
            photos = [post_data.get("photo")]
        
        buttons = post_data.get("buttons", [])

        buttons_markup = create_buttons_markup(buttons)

        clean_text = clean_unsupported_formatting(text)
        parse_mode = detect_parse_mode(clean_text)
        preview_text = format_text_for_preview(text)

        warnings = get_formatting_warnings(text)

        # Get layout preference (default: photo_top)
        layout = post_data.get("layout", "photo_top")

        if parse_mode == "HTML":
            prefix = "👀 <b>ПЕРЕДОГЛЯД:</b>\n\n"
        elif parse_mode == "Markdown":
            prefix = "👀 **ПЕРЕДОГЛЯД:**\n\n"
        else:
            prefix = "👀 PЕРЕДОГЛЯД:\n\n"

        # Handle new media format
        if media_list:
            if len(media_list) == 1:
                media_item = media_list[0]
                if media_item['type'] == 'photo':
                    if layout == "photo_bottom":
                        # Upload photo to telegra.ph for a single-message preview (image under text)
                        try:
                            telegraph_url = await upload_photo_to_telegraph_by_file_id(context.bot, media_item['file_id'])
                            logger.info(f"Telegraph URL result: {telegraph_url}")
                        except Exception as e:
                            logger.error(f"Error uploading to Telegraph: {e}")
                            telegraph_url = None
                        
                        if telegraph_url:
                            # Prepare text without URLs to avoid double previews
                            original_text = post_data.get("text", "")
                            import re
                            text_without_urls = re.sub(r'<a[^>]*>.*?</a>', '', original_text, flags=re.IGNORECASE)
                            text_without_urls = re.sub(r'https?://\S+', '', text_without_urls)
                            text_without_urls = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text_without_urls)
                            text_without_urls = re.sub(r'\s+', ' ', text_without_urls).strip()

                            # Use blockquote to show as a quote
                            quoted = f"<blockquote>{format_text_for_preview(text_without_urls)}</blockquote>"
                            body = f"{prefix}{quoted}\n\n{telegraph_url}"
                            
                            await update.effective_message.reply_text(
                                body,
                                parse_mode="HTML",
                                reply_markup=buttons_markup,
                                disable_web_page_preview=False,
                            )
                        else:
                            # Fallback: photo caption variant with warning
                            await update.effective_message.reply_text(
                                "⚠️ Не вдалося завантажити фото на telegra.ph. Відправляю стандартний попередній перегляд."
                            )
                            await update.effective_message.reply_photo(
                                photo=media_item['file_id'],
                                caption=f"{prefix}{preview_text}",
                                reply_markup=buttons_markup,
                                parse_mode=parse_mode,
                            )
                    else:
                        # Default: photo with caption (photo on top)
                        await update.effective_message.reply_photo(
                            photo=media_item['file_id'],
                            caption=f"{prefix}{preview_text}",
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                elif media_item['type'] == 'video':
                    await update.effective_message.reply_video(
                        video=media_item['file_id'],
                        caption=f"{prefix}{preview_text}",
                        reply_markup=buttons_markup,
                        parse_mode=parse_mode,
                    )
                elif media_item['type'] == 'document':
                    await update.effective_message.reply_document(
                        document=media_item['file_id'],
                        caption=f"{prefix}{preview_text}",
                        reply_markup=buttons_markup,
                        parse_mode=parse_mode,
                    )
            else:
                # Multiple media - send as media group (only photos supported in media groups)
                photo_media = [m for m in media_list if m['type'] == 'photo']
                other_media = [m for m in media_list if m['type'] != 'photo']
                
                if photo_media:
                    media = []
                    for idx, media_item in enumerate(photo_media):
                        if idx == 0:
                            media.append(
                                InputMediaPhoto(
                                    media=media_item['file_id'],
                                    caption=f"{prefix}{preview_text}",
                                    parse_mode=parse_mode,
                                )
                            )
                        else:
                            media.append(InputMediaPhoto(media=media_item['file_id']))
                    await update.effective_message.reply_media_group(media)
                
                # Send other media types separately
                for media_item in other_media:
                    if media_item['type'] == 'video':
                        await update.effective_message.reply_video(
                            video=media_item['file_id'],
                            caption=preview_text if not photo_media else None,
                            parse_mode=parse_mode if not photo_media else None,
                        )
                    elif media_item['type'] == 'document':
                        await update.effective_message.reply_document(
                            document=media_item['file_id'],
                            caption=preview_text if not photo_media else None,
                            parse_mode=parse_mode if not photo_media else None,
                        )
                
                if buttons_markup:
                    button_text = "🔗"
                    await update.effective_message.reply_text(
                        text=button_text, reply_markup=buttons_markup
                    )
        # Handle old photos format
        elif photos:
            if len(photos) == 1:
                await update.effective_message.reply_photo(
                    photo=photos[0],
                    caption=f"{prefix}{preview_text}",
                    reply_markup=buttons_markup,
                    parse_mode=parse_mode,
                )
            else:
                media = []
                for idx, fid in enumerate(photos):
                    if idx == 0:
                        media.append(
                            InputMediaPhoto(
                                media=fid,
                                caption=f"{prefix}{preview_text}",
                                parse_mode=parse_mode,
                            )
                        )
                    else:
                        media.append(InputMediaPhoto(media=fid))
                await update.effective_message.reply_media_group(media)
                if buttons_markup:
                    button_text = "🔗"
                    await update.effective_message.reply_text(
                        text=button_text, reply_markup=buttons_markup
                    )
        else:
            await update.effective_message.reply_text(
                f"{prefix}{preview_text}",
                reply_markup=buttons_markup,
                parse_mode=parse_mode,
            )
        if warnings:
            warning_text = "⚠️ *Увага:*\n" + "\n".join(f"• {w}" for w in warnings)
            await update.effective_message.reply_text(
                warning_text, parse_mode="Markdown"
            )

    async def send_post_job(self, channel_id, post_data, user_id, context=None):
        """function that is called by scheduler to send post."""
        import os
        import re

        from telegram.ext import Application

        bot = (
            context.bot
            if context
            else Application.builder().token(os.getenv("BOT_TOKEN")).build().bot
        )
        buttons_markup = create_buttons_markup(post_data.get("buttons"))

        try:
            # Resolve chat_id: support both @username and numeric -100... ids
            def _resolve_chat_id(raw_id):
                s = str(raw_id).strip()
                if s.startswith("-100") and s[1:].isdigit():
                    return int(s)
                if s.lstrip("-").isdigit():
                    # Any other numeric id
                    return int(s)
                s = s.lstrip("@")
                return f"@{s}"

            chat_id = _resolve_chat_id(channel_id)
            clean_channel_id = str(channel_id).lstrip("@")

            # Check for new media format first
            media_list = post_data.get("media", [])
            photos = post_data.get("photos")
            
            # Fallback to old photos format
            if not media_list and not photos and post_data.get("photo"):
                photos = [post_data.get("photo")]

            text = post_data.get("text", "")
            clean_text = clean_unsupported_formatting(text)
            parse_mode = detect_parse_mode(clean_text)

            # Get layout preference
            layout = post_data.get("layout", "photo_top")

            # Handle new media format
            if media_list:
                if len(media_list) == 1:
                    media_item = media_list[0]
                    if media_item['type'] == 'photo':
                        if layout == "photo_bottom":
                            # Use single message with link preview via telegra.ph
                            telegraph_url = await upload_photo_to_telegraph_by_file_id(bot, media_item['file_id'])
                            
                            if telegraph_url:
                                # Remove URLs from text to avoid double previews
                                text_without_urls = re.sub(r'<a[^>]*>.*?</a>', '', clean_text, flags=re.IGNORECASE)
                                text_without_urls = re.sub(r'https?://\S+', '', text_without_urls)
                                text_without_urls = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text_without_urls)
                                text_without_urls = re.sub(r'\s+', ' ', text_without_urls).strip()
                                
                                # Format as blockquote with Telegraph link below
                                quoted = f"<blockquote>{text_without_urls}</blockquote>"
                                body = f"{quoted}\n\n{telegraph_url}"
                                
                                sent_message = await bot.send_message(
                                    chat_id=chat_id,
                                    text=body,
                                    parse_mode="HTML",
                                    reply_markup=buttons_markup,
                                    disable_web_page_preview=False,
                                )
                            else:
                                # Fallback to normal captioned photo
                                sent_message = await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                        else:
                            # Default: photo on top
                            has_url = bool(re.search(r'https?://\S+', clean_text))
                            
                            if has_url:
                                # Send photo with caption (disable link preview)
                                sent_message = await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=media_item['file_id'],
                                    caption=clean_text,
                                    parse_mode=parse_mode,
                                    reply_markup=buttons_markup,
                                    disable_web_page_preview=True,
                                )
                            else:
                                # No URLs - standard photo with caption
                                sent_message = await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                    elif media_item['type'] == 'video':
                        sent_message = await bot.send_video(
                            chat_id=chat_id,
                            video=media_item['file_id'],
                            caption=clean_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                    elif media_item['type'] == 'document':
                        sent_message = await bot.send_document(
                            chat_id=chat_id,
                            document=media_item['file_id'],
                            caption=clean_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                else:
                    # Multiple media - send as media group
                    photo_media = [m for m in media_list if m['type'] == 'photo']
                    other_media = [m for m in media_list if m['type'] != 'photo']
                    
                    if photo_media:
                        media = []
                        for idx, media_item in enumerate(photo_media):
                            if idx == 0:
                                media.append(
                                    InputMediaPhoto(
                                        media=media_item['file_id'],
                                        caption=clean_text,
                                        parse_mode=parse_mode,
                                    )
                                )
                            else:
                                media.append(InputMediaPhoto(media=media_item['file_id']))
                        sent_messages = await bot.send_media_group(
                            chat_id=chat_id, media=media
                        )
                        sent_message = sent_messages[0]
                    else:
                        # No photos, send first media as main message
                        if other_media:
                            media_item = other_media[0]
                            if media_item['type'] == 'video':
                                sent_message = await bot.send_video(
                                    chat_id=chat_id,
                                    video=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                            elif media_item['type'] == 'document':
                                sent_message = await bot.send_document(
                                    chat_id=chat_id,
                                    document=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                            # Send remaining media separately
                            for remaining_media in other_media[1:]:
                                if remaining_media['type'] == 'video':
                                    await bot.send_video(
                                        chat_id=chat_id,
                                        video=remaining_media['file_id'],
                                    )
                                elif remaining_media['type'] == 'document':
                                    await bot.send_document(
                                        chat_id=chat_id,
                                        document=remaining_media['file_id'],
                                    )
                    
                    if buttons_markup and (len(photo_media) > 1 or len(other_media) > 1):
                        button_text = "🔗"
                        buttons = post_data.get("buttons", [])
                        for i, button in enumerate(buttons):
                            button_text += f" [{i+1}]"
                        await bot.send_message(
                            chat_id=chat_id,
                            text=button_text,
                            reply_markup=buttons_markup,
                        )
            # Handle old photos format
            elif photos:
                if len(photos) == 1:
                    sent_message = await bot.send_photo(
                        chat_id=chat_id,
                        photo=photos[0],
                        caption=clean_text,
                        reply_markup=buttons_markup,
                        parse_mode=parse_mode,
                    )
                else:
                    media = []
                    for idx, fid in enumerate(photos):
                        if idx == 0:
                            media.append(
                                InputMediaPhoto(
                                    media=fid, caption=clean_text, parse_mode=parse_mode
                                )
                            )
                        else:
                            media.append(InputMediaPhoto(media=fid))
                    sent_messages = await bot.send_media_group(
                        chat_id=chat_id, media=media
                    )
                    sent_message = sent_messages[0]
                    if buttons_markup:
                        button_text = "🔗"
                        buttons = post_data.get("buttons", [])
                        for i, button in enumerate(buttons):
                            button_text += f" [{i+1}]"
                        await bot.send_message(
                            chat_id=chat_id,
                            text=button_text,
                            reply_markup=buttons_markup,
                        )
            else:
                # No media: send text message
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=clean_text,
                    reply_markup=buttons_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )
            
            try:
                # Store media data
                media_to_store = None
                media_type = None
                
                if media_list:
                    media_to_store = str(media_list)
                    if media_list:
                        media_type = media_list[0]['type']
                elif photos:
                    media_to_store = str(photos)
                    media_type = 'photo'
                
                save_published_post(
                    user_id,
                    channel_id,
                    sent_message.message_id,
                    text,
                    media_to_store,
                    media_type,
                    post_data.get("buttons"),
                )
            except Exception as _:
                pass

            admin_keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати",
                        callback_data=f"editpublished_{sent_message.message_id}_{channel_id}",
                    ),
                    InlineKeyboardButton(
                        "🗑 Видалити",
                        callback_data=f"deletepublished_{sent_message.message_id}_{channel_id}",
                    ),
                ]
            ]
            await bot.send_message(
                chat_id=user_id,
                text=f"Пост опубліковано в @{clean_channel_id}. Ви можете ним керувати.",
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
            )

        except Exception as e:
            logger.error(f"Error sending post to {channel_id}: {e}")
            clean_channel_id = channel_id.lstrip("@")
            await bot.send_message(
                user_id,
                f"❌ Не вдалося надіслати пост у канал @{clean_channel_id}. {e}",
            )
            # Re-raise the exception so the caller knows it failed
            raise