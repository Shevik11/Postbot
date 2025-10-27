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
    create_layout_keyboard,
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


class PostHandlers:
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
        
        # No need to modify text for photo_bottom - we'll show original text

        if parse_mode == "HTML":
            prefix = "👀 <b>ПЕРЕДОГЛЯД:</b>\n\n"
        elif parse_mode == "Markdown":
            prefix = "👀 **ПЕРЕДОГЛЯД:**\n\n"
        else:
            prefix = "👀 ПЕРЕДОГЛЯД:\n\n"

        # Handle new media format
        if media_list:
            if len(media_list) == 1:
                media_item = media_list[0]
                # Check if it's a dict with 'type' key (new format) or just file_id (old format)
                if isinstance(media_item, dict) and 'type' in media_item:
                    media_type = media_item['type']
                    file_id = media_item['file_id']
                else:
                    # Old format - assume it's a photo
                    media_type = 'photo'
                    file_id = media_item
                
                if media_type == 'photo':
                    if layout == "photo_bottom":
                        # Get original text and remove URLs
                        original_text = post_data.get("text", "")
                        import re
                        text_without_urls = original_text
                        url_pattern = r'https?://\S+'
                        urls = re.findall(url_pattern, original_text)
                        if urls:
                            for url in urls:
                                text_without_urls = text_without_urls.replace(url, '').strip()
                            text_without_urls = re.sub(r'\s+', ' ', text_without_urls).strip()
                        
                        preview_clean = format_text_for_preview(text_without_urls)
                        # Send text without URLs but keep formatting
                        await update.effective_message.reply_text(
                            f"{prefix}{preview_clean}",
                            parse_mode="HTML",  # Keep HTML formatting
                        )
                        # Then send photo separately
                        await update.effective_message.reply_photo(
                            photo=file_id,
                            reply_markup=buttons_markup,
                        )
                    else:
                        # Default: photo with caption (photo on top)
                        await update.effective_message.reply_photo(
                            photo=file_id,
                            caption=f"{prefix}{preview_text}",
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                elif media_type == 'video':
                    await update.effective_message.reply_video(
                        video=file_id,
                        caption=f"{prefix}{preview_text}",
                        reply_markup=buttons_markup,
                        parse_mode=parse_mode,
                    )
                elif media_type == 'document':
                    await update.effective_message.reply_document(
                        document=file_id,
                        caption=f"{prefix}{preview_text}",
                        reply_markup=buttons_markup,
                        parse_mode=parse_mode,
                    )
            else:
                # Multiple media - send as media group (only photos supported in media groups)
                photo_media = []
                other_media = []
                
                for m in media_list:
                    if isinstance(m, dict) and 'type' in m:
                        if m['type'] == 'photo':
                            photo_media.append(m)
                        else:
                            other_media.append(m)
                    else:
                        # Old format - assume it's a photo
                        photo_media.append({'file_id': m, 'type': 'photo'})
                
                if photo_media:
                    media = []
                    for idx, media_item in enumerate(photo_media):
                        file_id = media_item['file_id'] if isinstance(media_item, dict) else media_item
                        if idx == 0:
                            media.append(
                                InputMediaPhoto(
                                    media=file_id,
                                    caption=f"{prefix}{preview_text}",
                                    parse_mode=parse_mode,
                                )
                            )
                        else:
                            media.append(InputMediaPhoto(media=file_id))
                    await update.effective_message.reply_media_group(media)
                
                # Send other media types separately
                for media_item in other_media:
                    file_id = media_item['file_id'] if isinstance(media_item, dict) else media_item
                    media_type = media_item['type'] if isinstance(media_item, dict) else 'photo'
                    
                    if media_type == 'video':
                        await update.effective_message.reply_video(
                            video=file_id,
                            caption=preview_text if not photo_media else None,
                            parse_mode=parse_mode if not photo_media else None,
                        )
                    elif media_type == 'document':
                        await update.effective_message.reply_document(
                            document=file_id,
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
                photo_item = photos[0]
                # Handle both old format (just file_id) and new format (dict with file_id and type)
                if isinstance(photo_item, dict) and 'file_id' in photo_item:
                    file_id = photo_item['file_id']
                else:
                    file_id = photo_item
                
                await update.effective_message.reply_photo(
                    photo=file_id,
                    caption=f"{prefix}{preview_text}",
                    reply_markup=buttons_markup,
                    parse_mode=parse_mode,
                )
            else:
                media = []
                for idx, photo_item in enumerate(photos):
                    # Handle both old format (just file_id) and new format (dict with file_id and type)
                    if isinstance(photo_item, dict) and 'file_id' in photo_item:
                        file_id = photo_item['file_id']
                    else:
                        file_id = photo_item
                    
                    if idx == 0:
                        media.append(
                            InputMediaPhoto(
                                media=file_id,
                                caption=f"{prefix}{preview_text}",
                                parse_mode=parse_mode,
                            )
                        )
                    else:
                        media.append(InputMediaPhoto(media=file_id))
                await update.effective_message.reply_media_group(media)
                if buttons_markup:
                    button_text = "🔗"
                    await update.effective_message.reply_text(
                        text=button_text, reply_markup=buttons_markup
                    )
        else:
            # No media - send text only
            # Check if text contains URLs
            import re
            url_pattern = r'https?://\S+'
            urls = re.findall(url_pattern, clean_text)
            
            if urls:
                # If there are URLs, handle layout positioning
                from telegram import LinkPreviewOptions
                first_url = urls[0]
                layout = post_data.get("layout", "photo_top")  # "photo_top" або "photo_bottom"
                is_telegraph = 'telegra.ph' in first_url
                
                # Extract text without URLs
                text_without_urls = re.sub(r'https?://\S+', '', clean_text).strip()
                
                if is_telegraph:
                    # Для Telegraph - витягни фото
                    try:
                        import requests
                        from bs4 import BeautifulSoup
                        
                        response = requests.get(first_url, timeout=5)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        images = soup.find_all('img')
                        
                        if images:
                            photo_url = images[0]['src']
                            if not photo_url.startswith('http'):
                                photo_url = f"https://telegra.ph{photo_url}"
                            
                            if layout == "photo_bottom":
                                # ТЕКСТ ЗВЕРХУ, ФОТО ЗНИЗУ
                                if text_without_urls:
                                    await update.effective_message.reply_text(
                                        text=text_without_urls,
                                        parse_mode=parse_mode,
                                    )
                                
                                # Потім фото
                                await update.effective_message.reply_photo(
                                    photo=photo_url,
                                    reply_markup=buttons_markup,
                                )
                            else:
                                # ФОТО ЗВЕРХУ, текст в caption (дефолт)
                                await update.effective_message.reply_photo(
                                    photo=photo_url,
                                    caption=text_without_urls if text_without_urls else None,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                        else:
                            # Немає фото - fallback
                            await update.effective_message.reply_text(
                                text=preview_text,
                                reply_markup=buttons_markup,
                                parse_mode=parse_mode,
                            )
                    except Exception as e:
                        # Fallback на звичайне повідомлення
                        await update.effective_message.reply_text(
                            text=preview_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                else:
                    # Звичайний лінк (не Telegraph)
                    if layout == "photo_bottom":
                        # Для звичайних лінків - фото знизу
                        await update.effective_message.reply_text(
                            text=preview_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                            link_preview_options=LinkPreviewOptions(
                                prefer_large_media=True,
                                show_above_text=False,  # ФОТО ЗНИЗУ
                            )
                        )
                    else:
                        # Фото зверху (дефолт)
                        await update.effective_message.reply_text(
                            text=preview_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                            link_preview_options=LinkPreviewOptions(
                                prefer_large_media=True,
                                show_above_text=True,  # ФОТО ЗВЕРХУ
                            )
                        )
            else:
                # No URLs - send normally
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
        """Function that is called by scheduler to send post."""
        import os
        from telegram import InputMediaPhoto, LinkPreviewOptions
        from telegram.ext import Application
        import re
        from bs4 import BeautifulSoup
        import requests

        bot = (
            context.bot
            if context
            else Application.builder().token(os.getenv("BOT_TOKEN")).build().bot
        )
        buttons_markup = create_buttons_markup(post_data.get("buttons"))
        clean_channel_id = channel_id.lstrip("@")

        # Extract key data early
        layout = post_data.get("layout", "photo_top")  # Default to photo_top
        # DEBUG: Log layout for troubleshooting
        print(f"Channel: @{clean_channel_id}, Layout: {layout}, Post ID/User: {user_id}")

        text = post_data.get("text", "")
        clean_text = clean_unsupported_formatting(text)
        parse_mode = detect_parse_mode(clean_text)

        # Handle new media format
        media_list = post_data.get("media", [])
        # Fallback to old photos format
        photos = post_data.get("photos", [])
        if not media_list and not photos and post_data.get("photo"):
            photos = [post_data.get("photo")]
        if photos and not media_list:
            media_list = [{'type': 'photo', 'file_id': fid} for fid in photos]

        # Prepare text without URLs for photo_bottom scenarios
        text_without_urls = re.sub(r'https?://\S+', '', clean_text).strip()
        text_without_urls = re.sub(r'\s+', ' ', text_without_urls).strip()

        # Check if there are URLs in text
        urls = re.findall(r'https?://\S+', clean_text)
        has_urls = bool(urls)

        try:

            # Handle new media format
            if media_list:
                if len(media_list) == 1:
                    media_item = media_list[0]
                    if media_item['type'] == 'photo':
                        # Check if text has URLs for link preview
                        import re
                        has_url = bool(re.search(r'https?://\S+', clean_text))
                        
                        if has_url:
                            # Send photo with caption (text will be above photo)
                            sent_message = await bot.send_photo(
                                chat_id=f"@{clean_channel_id}",
                                photo=media_item['file_id'],
                                caption=clean_text,
                                parse_mode=parse_mode,
                                reply_markup=buttons_markup,
                                disable_web_page_preview=True,  # Disable link preview
                            )
                        else:
                            # No URLs - use standard photo with caption
                            sent_message = await bot.send_photo(
                                chat_id=f"@{clean_channel_id}",
                                photo=media_item['file_id'],
                                caption=clean_text,
                                reply_markup=buttons_markup,
                                parse_mode=parse_mode,
                            )
                    elif media_item['type'] == 'video':
                        sent_message = await bot.send_video(
                            chat_id=f"@{clean_channel_id}",
                            video=media_item['file_id'],
                            caption=clean_text,
                            reply_markup=buttons_markup,
                            parse_mode=parse_mode,
                        )
                    elif media_item['type'] == 'document':
                        sent_message = await bot.send_document(
                            chat_id=f"@{clean_channel_id}",
                            document=media_item['file_id'],
                            caption=clean_text,
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
                                        caption=clean_text,
                                        parse_mode=parse_mode,
                                    )
                                )
                            else:
                                media.append(InputMediaPhoto(media=media_item['file_id']))
                        sent_messages = await bot.send_media_group(
                            chat_id=f"@{clean_channel_id}", media=media
                        )
                        sent_message = sent_messages[0]
                    else:
                        # No photos, send first media as main message
                        if other_media:
                            media_item = other_media[0]
                            if media_item['type'] == 'video':
                                sent_message = await bot.send_video(
                                    chat_id=f"@{clean_channel_id}",
                                    video=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                            elif media_item['type'] == 'document':
                                sent_message = await bot.send_document(
                                    chat_id=f"@{clean_channel_id}",
                                    document=media_item['file_id'],
                                    caption=clean_text,
                                    reply_markup=buttons_markup,
                                    parse_mode=parse_mode,
                                )
                            # Send remaining media separately
                            for remaining_media in other_media[1:]:
                                if remaining_media['type'] == 'video':
                                    await bot.send_video(
                                        chat_id=f"@{clean_channel_id}",
                                        video=remaining_media['file_id'],
                                    )
                                elif remaining_media['type'] == 'document':
                                    await bot.send_document(
                                        chat_id=f"@{clean_channel_id}",
                                        document=remaining_media['file_id'],
                                    )
                    
                    if buttons_markup and (len(photo_media) > 1 or len(other_media) > 1):
                        button_text = "🔗"
                        buttons = post_data.get("buttons", [])
                        for i, button in enumerate(buttons):
                            button_text += f" [{i+1}]"
                        await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=button_text,
                            reply_markup=buttons_markup,
                        )
            # Handle old photos format
            elif photos:
                if len(photos) == 1:
                    sent_message = await bot.send_photo(
                        chat_id=f"@{clean_channel_id}",
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
                        chat_id=f"@{clean_channel_id}", media=media
                    )
                    sent_message = sent_messages[0]
                    if buttons_markup:
                        button_text = "🔗"
                        buttons = post_data.get("buttons", [])
                        for i, button in enumerate(buttons):
                            button_text += f" [{i+1}]"
                        await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=button_text,
                            reply_markup=buttons_markup,
                        )
            else:
                if layout == "photo_bottom":
                    # Text above, media below: Send text first, then media without caption
                    text_to_send = text_without_urls if has_urls else clean_text
                    if text_to_send:
                        await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=text_to_send,
                            parse_mode=parse_mode,
                            disable_web_page_preview=True,  # Always disable to avoid unexpected previews
                        )
                    # Send media
                    if len(media_list) == 1:
                        media_item = media_list[0]
                        reply_markup = buttons_markup  # Attach buttons to media
                        if media_item['type'] == 'photo':
                            sent_message = await bot.send_photo(
                                chat_id=f"@{clean_channel_id}",
                                photo=media_item['file_id'],
                                reply_markup=reply_markup,
                            )
                        elif media_item['type'] == 'video':
                            sent_message = await bot.send_video(
                                chat_id=f"@{clean_channel_id}",
                                video=media_item['file_id'],
                                reply_markup=reply_markup,
                            )
                        elif media_item['type'] == 'document':
                            sent_message = await bot.send_document(
                                chat_id=f"@{clean_channel_id}",
                                document=media_item['file_id'],
                                reply_markup=reply_markup,
                            )
                    else:
                        # Multiple media: Send group/sequence, buttons on last or separate
                        sent_message = None
                        if photo_media:
                            media_group = [InputMediaPhoto(m['file_id']) for m in photo_media]
                            sent_messages = await bot.send_media_group(
                                chat_id=f"@{clean_channel_id}",
                                media=media_group,
                            )
                            sent_message = sent_messages[-1]
                        for m in other_media:
                            if m['type'] == 'video':
                                sent_message = await bot.send_video(
                                    chat_id=f"@{clean_channel_id}",
                                    video=m['file_id'],
                                )
                            elif m['type'] == 'document':
                                sent_message = await bot.send_document(
                                    chat_id=f"@{clean_channel_id}",
                                    document=m['file_id'],
                                )
                        if buttons_markup:
                            await bot.send_message(
                                chat_id=f"@{clean_channel_id}",
                                text="🔗",  # Placeholder for buttons
                                reply_markup=buttons_markup,
                            )
                else:
                    # photo_top: Media on top with caption
                    if len(media_list) == 1:
                        media_item = media_list[0]
                        caption = clean_text if not has_urls else text_without_urls
                        if media_item['type'] == 'photo':
                            sent_message = await bot.send_photo(
                                chat_id=f"@{clean_channel_id}",
                                photo=media_item['file_id'],
                                caption=caption,
                                parse_mode=parse_mode,
                                reply_markup=buttons_markup,
                                disable_web_page_preview=has_urls,
                            )
                        elif media_item['type'] == 'video':
                            sent_message = await bot.send_video(
                                chat_id=f"@{clean_channel_id}",
                                video=media_item['file_id'],
                                caption=caption,
                                parse_mode=parse_mode,
                                reply_markup=buttons_markup,
                            )
                        elif media_item['type'] == 'document':
                            sent_message = await bot.send_document(
                                chat_id=f"@{clean_channel_id}",
                                document=media_item['file_id'],
                                caption=caption,
                                parse_mode=parse_mode,
                                reply_markup=buttons_markup,
                            )
                    else:
                        # Multiple: Group with caption on first
                        caption = clean_text if not has_urls else text_without_urls
                        if photo_media:
                            media_group = []
                            for idx, m in enumerate(photo_media):
                                if idx == 0:
                                    media_group.append(InputMediaPhoto(m['file_id'], caption=caption, parse_mode=parse_mode))
                                else:
                                    media_group.append(InputMediaPhoto(m['file_id']))
                            sent_messages = await bot.send_media_group(
                                chat_id=f"@{clean_channel_id}",
                                media=media_group,
                            )
                            sent_message = sent_messages[0]
                        for idx, m in enumerate(other_media):
                            caption_to_use = caption if idx == 0 and not photo_media else None
                            parse_to_use = parse_mode if caption_to_use else None
                            if m['type'] == 'video':
                                sent_message = await bot.send_video(
                                    chat_id=f"@{clean_channel_id}",
                                    video=m['file_id'],
                                    caption=caption_to_use,
                                    parse_mode=parse_to_use,
                                )
                            elif m['type'] == 'document':
                                sent_message = await bot.send_document(
                                    chat_id=f"@{clean_channel_id}",
                                    document=m['file_id'],
                                    caption=caption_to_use,
                                    parse_mode=parse_to_use,
                                )
                        if buttons_markup:
                            await bot.send_message(
                                chat_id=f"@{clean_channel_id}",
                                text="🔗",
                                reply_markup=buttons_markup,
                            )
        
            # Text-only handling
        if not media_list:
            # No media: Text-only, possibly with URL previews
            if has_urls:
                first_url = urls[0]
                is_telegraph = 'telegra.ph' in first_url

                if is_telegraph:
                    # Extract image from Telegraph for manual handling
                    try:
                        response = requests.get(first_url, timeout=5)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        images = soup.find_all('img')

                        if images:
                            photo_url = images[0]['src']
                            if not photo_url.startswith('http'):
                                photo_url = f"https://telegra.ph{photo_url}"

                            if layout == "photo_bottom":
                                # Text above, photo below
                                if text_without_urls:
                                    await bot.send_message(
                                        chat_id=f"@{clean_channel_id}",
                                        text=text_without_urls,
                                        parse_mode=parse_mode,
                                    )
                                sent_message = await bot.send_photo(
                                    chat_id=f"@{clean_channel_id}",
                                    photo=photo_url,
                                    reply_markup=buttons_markup,
                                )
                            else:
                                # Photo top
                                sent_message = await bot.send_photo(
                                    chat_id=f"@{clean_channel_id}",
                                    photo=photo_url,
                                    caption=text_without_urls,
                                    parse_mode=parse_mode,
                                    reply_markup=buttons_markup,
                                )
                        else:
                            # No image: Fallback to text
                            sent_message = await bot.send_message(
                                chat_id=f"@{clean_channel_id}",
                                text=clean_text,
                                parse_mode=parse_mode,
                                reply_markup=buttons_markup,
                            )
                    except Exception:
                        # Fallback
                        sent_message = await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=clean_text,
                            parse_mode=parse_mode,
                            reply_markup=buttons_markup,
                        )
                    else:
                        # Non-Telegraph URLs: Use link preview options
                        show_above = layout != "photo_bottom"  # False for bottom
                        sent_message = await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=clean_text,
                            parse_mode=parse_mode,
                            reply_markup=buttons_markup,
                            link_preview_options=LinkPreviewOptions(
                                prefer_large_media=True,
                                show_above_text=show_above,
                            ),
                        )
                else:
                    # Pure text, no URLs
                    sent_message = await bot.send_message(
                        chat_id=f"@{clean_channel_id}",
                        text=clean_text,
                        parse_mode=parse_mode,
                        reply_markup=buttons_markup,
                    )
                    
                # Store media data
                media_to_store = None
                media_type = None
                
                if media_list:
                    media_to_store = str(media_list)
                    # Determine primary media type
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
                f"❌ Не вдалося надіслати пост у канал @{clean_channel_id}. Перевірте, чи бот є адміністратором з правами на публікацію.",
            )
            # Re-raise the exception so the caller knows it failed
            raise

    # --- CREATE POST ---
    async def create_post_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        context.user_data["new_post"] = {}
        await update.message.reply_text(
            "Надішліть текст поста або медіафайл (фото/відео/документ).",
            reply_markup=ReplyKeyboardMarkup(
                [["❌ Скасувати"]], resize_keyboard=True
            ),
        )
        return CREATE_POST_WAITING_FOR_CONTENT

    async def create_post_content(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.text == "❌ Скасувати":
            context.user_data.pop("new_post", None)
            await update.message.reply_text(
                "Створення поста скасовано.", reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

        new_post = context.user_data.get("new_post", {})
        
        # Handle text
        if update.message.text:
            new_post["text"] = update.message.text
        
        # Handle media
        media_list = new_post.get("media", [])
        
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            media_list.append({'type': 'photo', 'file_id': file_id})
        elif update.message.video:
            file_id = update.message.video.file_id
            media_list.append({'type': 'video', 'file_id': file_id})
        elif update.message.document:
            file_id = update.message.document.file_id
            media_list.append({'type': 'document', 'file_id': file_id})
        
        if media_list:
            new_post["media"] = media_list
        
        context.user_data["new_post"] = new_post
        
        keyboard = [
            ["➕ Додати ще медіа", "✅ Завершити"],
            ["🔘 Додати кнопки"],
            ["❌ Скасувати"]
        ]
        
        await update.message.reply_text(
            "Контент додано. Оберіть дію:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return CREATE_POST_ACTIONS

    async def create_post_actions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text
        
        if text == "❌ Скасувати":
            context.user_data.pop("new_post", None)
            await update.message.reply_text(
                "Створення поста скасовано.", reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        elif text == "✅ Завершити":
            return await self.create_post_choose_channels(update, context)
        elif text == "🔘 Додати кнопки":
            await update.message.reply_text(
                "Надішліть кнопки у форматі:\n"
                "Текст1 | URL1\n"
                "Текст2 | URL2",
                reply_markup=ReplyKeyboardMarkup(
                    [["❌ Скасувати"]], resize_keyboard=True
                ),
            )
            return CREATE_POST_WAITING_FOR_BUTTONS
        elif text == "➕ Додати ще медіа":
            await update.message.reply_text(
                "Надішліть ще медіафайл:",
                reply_markup=ReplyKeyboardMarkup(
                    [["✅ Завершити"], ["❌ Скасувати"]], resize_keyboard=True
                ),
            )
            return CREATE_POST_WAITING_FOR_CONTENT

    async def create_post_buttons(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.text == "❌ Скасувати":
            context.user_data.pop("new_post", None)
            await update.message.reply_text(
                "Створення поста скасовано.", reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

        button_text = update.message.text
        buttons = []
        for line in button_text.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 1)
                if len(parts) == 2:
                    text, url = parts
                    buttons.append({"text": text.strip(), "url": url.strip()})
        
        context.user_data["new_post"]["buttons"] = buttons
        
        keyboard = [
            ["➕ Додати ще медіа", "✅ Завершити"],
            ["❌ Скасувати"]
        ]
        
        await update.message.reply_text(
            f"Додано {len(buttons)} кнопок. Оберіть дію:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return CREATE_POST_ACTIONS

    async def create_post_choose_channels(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        new_post = context.user_data.get("new_post", {})
        
        # Get user channels
        user_id = update.effective_user.id
        channels = get_user_channels(user_id)
        
        if not channels:
            await update.message.reply_text(
                "У вас немає доданих каналів. Спочатку додайте канал командою /addchannel",
                reply_markup=ReplyKeyboardRemove(),
            )
            context.user_data.pop("new_post", None)
            return ConversationHandler.END
        
        keyboard = []
        for channel_id, channel_name in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 {channel_name}",
                    callback_data=f"createpost_channel_{channel_id}"
                )
            ])
        
        await update.message.reply_text(
            "Оберіть канал для публікації:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        
        return ConversationHandler.END

    async def create_post_select_channel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()
        
        channel_id = query.data.replace("createpost_channel_", "")
        new_post = context.user_data.get("new_post", {})
        
        if not new_post:
            await query.edit_message_text("Пост не знайдено. Почніть створення заново з /createpost")
            return
        
        # Send post immediately
        try:
            await self.send_post_job(channel_id, new_post, query.from_user.id, context)
            await query.edit_message_text("✅ Пост успішно опубліковано!")
        except Exception as e:
            logger.error(f"Error publishing post: {e}")
            await query.edit_message_text(f"❌ Помилка при публікації поста: {e}")
        
        context.user_data.pop("new_post", None)

    # --- EDIT POST ---
    async def edit_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.edit_message_text("❌ Невірний формат даних")
            return
        
        action = parts[0]  # 'editpublished'
        message_id = int(parts[1])
        channel_id = "_".join(parts[2:])
        
        # Store edit context
        context.user_data["edit_post"] = {
            "message_id": message_id,
            "channel_id": channel_id
        }
        
        keyboard = [
            [InlineKeyboardButton("✏️ Текст", callback_data=f"edittext_{message_id}_{channel_id}")],
            [InlineKeyboardButton("🔘 Кнопки", callback_data=f"editbuttons_{message_id}_{channel_id}")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="canceledit")]
        ]
        
        await query.edit_message_text(
            "Що ви хочете редагувати?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def delete_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.edit_message_text("❌ Невірний формат даних")
            return
        
        action = parts[0]  # 'deletepublished'
        message_id = int(parts[1])
        channel_id = "_".join(parts[2:])
        
        # Confirm deletion
        keyboard = [
            [
                InlineKeyboardButton("✅ Так", callback_data=f"confirmdel_{message_id}_{channel_id}"),
                InlineKeyboardButton("❌ Ні", callback_data="canceldel")
            ]
        ]
        
        await query.edit_message_text(
            "Ви впевнені, що хочете видалити цей пост?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def confirm_delete_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.edit_message_text("❌ Невірний формат даних")
            return
        
        action = parts[0]  # 'confirmdel'
        message_id = int(parts[1])
        channel_id = "_".join(parts[2:])
        
        try:
            # Delete message from channel
            bot = context.bot
            await bot.delete_message(
                chat_id=f"@{channel_id.lstrip('@')}",
                message_id=message_id
            )
            
            await query.edit_message_text("✅ Пост успішно видалено!")
        except Exception as e:
            logger.error(f"Error deleting post: {e}")
            await query.edit_message_text(f"❌ Помилка при видаленні поста: {e}")

    # Utility handlers
    async def cancel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Редагування скасовано.")
        context.user_data.pop("edit_post", None)

    async def cancel_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Видалення скасовано.")

    # --- SCHEDULED POSTS ---
    async def list_scheduled_posts(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        user_id = update.effective_user.id
        scheduled = get_scheduled_posts(user_id)
        
        if not scheduled:
            await update.message.reply_text("У вас немає запланованих постів.")
            return
        
        for post_id, channel_id, post_time, post_data in scheduled:
            post_text = post_data.get("text", "Без тексту")[:50]
            keyboard = [
                [
                    InlineKeyboardButton(
                        "❌ Скасувати",
                        callback_data=f"cancelscheduled_{post_id}"
                    )
                ]
            ]
            await update.message.reply_text(
                f"📅 Запланований пост в {channel_id}\n"
                f"Час: {post_time}\n"
                f"Текст: {post_text}...",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    async def cancel_scheduled_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()
        
        post_id = int(query.data.replace("cancelscheduled_", ""))
        
        # Remove from database
        delete_scheduled_post(post_id)
        
        # Remove job from scheduler
        if hasattr(self, 'scheduler'):
            try:
                self.scheduler.remove_job(f"post_{post_id}")
            except:
                pass
        
        await query.edit_message_text("✅ Запланований пост скасовано.")

    # Preview post before scheduling/sending
    async def preview_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, post_data: dict
    ):
        """Send a preview of the post to the user"""
        text = post_data.get("text", "")
        media_list = post_data.get("media", [])
        photos = post_data.get("photos", [])
        buttons = post_data.get("buttons", [])
        
        buttons_markup = create_buttons_markup(buttons) if buttons else None
        
        try:
            if media_list:
                if len(media_list) == 1:
                    media_item = media_list[0]
                    if media_item['type'] == 'photo':
                        await update.effective_message.reply_photo(
                            photo=media_item['file_id'],
                            caption=f"📝 Попередній перегляд:\n\n{text}",
                            reply_markup=buttons_markup,
                        )
                    elif media_item['type'] == 'video':
                        await update.effective_message.reply_video(
                            video=media_item['file_id'],
                            caption=f"📝 Попередній перегляд:\n\n{text}",
                            reply_markup=buttons_markup,
                        )
                    elif media_item['type'] == 'document':
                        await update.effective_message.reply_document(
                            document=media_item['file_id'],
                            caption=f"📝 Попередній перегляд:\n\n{text}",
                            reply_markup=buttons_markup,
                        )
                else:
                    # Multiple media - just show text preview
                    await update.effective_message.reply_text(
                        f"📝 Попередній перегляд:\n\n{text}\n\n(+ {len(media_list)} медіафайлів)",
                        reply_markup=buttons_markup,
                    )
            elif photos:
                if len(photos) == 1:
                    await update.effective_message.reply_photo(
                        photo=photos[0],
                        caption=f"📝 Попередній перегляд:\n\n{text}",
                        reply_markup=buttons_markup,
                    )
                else:
                    await update.effective_message.reply_text(
                        f"📝 Попередній перегляд:\n\n{text}\n\n(+ {len(photos)} фото)",
                        reply_markup=buttons_markup,
                    )
            else:
                await update.effective_message.reply_text(
                    f"📝 Попередній перегляд:\n\n{text}",
                    reply_markup=buttons_markup,
                )
            
            warnings = []
            clean_text = clean_unsupported_formatting(text)
            if clean_text != text:
                warnings.append("Деяке форматування було видалено")
            
            if warnings:
                warning_text = "⚠️ *Увага:*\n" + "\n".join(f"• {w}" for w in warnings)
                await update.effective_message.reply_text(
                    warning_text, parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error previewing post: {e}")
            await update.effective_message.reply_text(
                f"❌ Помилка при попередньому перегляді: {e}"
            )

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
        await self.preview_post(update, context, "new_post")
        await update.message.reply_text(
            "Пост готовий. Надіслати зараз чи запланувати?",
            reply_markup=create_schedule_keyboard(),
        )
        from config import SCHEDULE_TIME
        return SCHEDULE_TIME

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
        return await self.schedule_menu(update, context)

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

    # --- PREVIEW AND SCHEDULE ---
    async def schedule_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.preview_post(update, context, "new_post")
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
            return await self.select_channel_menu(update, context)
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
            return await self.edit_photo_from_schedule(update, context)
        elif query.data == "edit_buttons":
            return await self.edit_buttons_from_schedule(update, context)

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
            return await self.select_channel_menu(update, context)
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
                return await self.schedule_menu_from_callback(update, context)

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

    async def schedule_menu_from_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show schedule menu after callback (not from message)."""
        await self.preview_post(update, context, "new_post")

        await update.callback_query.message.reply_text(
            "Пост готовий. Надіслати зараз чи запланувати?",
            reply_markup=create_schedule_keyboard(),
        )
        from config import SCHEDULE_TIME

        return SCHEDULE_TIME

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
                post_data.get("layout", "photo_top"),  # Add layout parameter
            )
            await query.edit_message_text(
                f"✅ Пост заплановано на {publish_time.strftime('%Y-%m-%d %H:%M')} у канал {channel_id}."
            )
        else:
            # immediate send
            try:
                await self.send_post_job(
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
            return await self.add_buttons_handler(update, context)

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
                await self.preview_post(update, context, "new_post")
                await query.message.reply_text(
                    "Пост готовий. Надіслати зараз чи запланувати?",
                    reply_markup=create_schedule_keyboard(),
                )
                from config import SCHEDULE_TIME
                return SCHEDULE_TIME
            else:
                # Continue to buttons (normal flow)
                return await self.add_buttons_handler(update, context)

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

    async def change_layout_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle layout change button."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🖼️ Оберіть розташування фото:",
            reply_markup=create_layout_keyboard()
        )
        return SCHEDULE_TIME

    async def handle_layout_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle layout choice selection."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "layout_photo_top":
            context.user_data["new_post"]["layout"] = "photo_top"
            print(f"DEBUG: Layout set to photo_top for user {update.effective_user.id}")
            await query.edit_message_text("✅ Розташування: фото зверху")
        elif data == "layout_photo_bottom":
            context.user_data["new_post"]["layout"] = "photo_bottom"
            print(f"DEBUG: Layout set to photo_bottom for user {update.effective_user.id}")
            await query.edit_message_text("✅ Розташування: фото знизу")
        elif data == "back_to_schedule":
            await query.edit_message_text(
                "✅ Медіа налаштовано! Тепер оберіть час публікації:",
                reply_markup=create_schedule_keyboard()
            )
            return SCHEDULE_TIME
        
        # Show schedule keyboard
        await query.message.reply_text(
            "✅ Медіа налаштовано! Тепер оберіть час публікації:",
            reply_markup=create_schedule_keyboard()
        )
        return SCHEDULE_TIME
