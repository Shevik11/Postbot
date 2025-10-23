import ast

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from config import (
    DELETE_PUBLISHED_CONFIRM,
    EDIT_PUBLISHED_MENU,
    EDIT_PUBLISHED_TEXT,
    MAIN_MENU,
    VIEW_PUBLISHED_POSTS,
)
from database import get_published_post, update_published_post
from handlers import PostHandlers
from scheduled_handlers import ScheduledPostHandlers
from utils import (
    clean_unsupported_formatting,
    create_buttons_markup,
    create_main_keyboard,
    create_photo_management_keyboard,
    detect_parse_mode,
    entities_to_html,
    parse_buttons,
)


class ChannelBot:
    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler
        self.post_handlers = PostHandlers(self)
        self.scheduled_handlers = ScheduledPostHandlers(self)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """main menu of bot."""
        welcome_text = "Вітаю! Я допоможу вам керувати публікаціями у вашому каналі."
        await update.message.reply_text(
            welcome_text, reply_markup=create_main_keyboard()
        )
        return MAIN_MENU

    async def main_menu_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """handle choice from main menu."""
        text = update.message.text
        if "Створити пост" in text:
            return await self.post_handlers.create_post_start(update, context)
        elif "Відкладені пости" in text:
            return await self.scheduled_handlers.view_scheduled_posts(update, context)
        elif "Існуючі пости" in text:
            return await self.view_published_posts(update, context)
        
        return MAIN_MENU

    async def edit_delete_published_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """handler for editing/deleting published posts."""
        from telegram.ext import ConversationHandler

        query = update.callback_query
        await query.answer()
        
        # Handle different callback formats
        if query.data.startswith("ep_"):
            # New edit callbacks (ep_edit_text, ep_edit_photos, etc.)
            return await self.handle_edit_callbacks(update, context)
        else:
            # Old format callbacks (editpublished_msgId_channelId, deletepublished_msgId_channelId)
            try:
                action, msg_id, channel_id = query.data.split("_")
            except ValueError:
                await query.message.reply_text("❌ Невідомий формат callback.")
                return ConversationHandler.END

        if action == "editpublished":
            # load published post data
            row = get_published_post(channel_id, int(msg_id))
            if not row:
                await query.message.reply_text(
                    "❌ Опублікований пост не знайдено в базі."
                )
                return ConversationHandler.END
            user_id, text, photo_id, buttons = row
            photos = []
            if photo_id:
                try:
                    photos = (
                        ast.literal_eval(photo_id)
                        if photo_id.startswith("[")
                        else [photo_id]
                    )
                except Exception:
                    photos = [photo_id]
            if buttons:
                try:
                    buttons = ast.literal_eval(buttons)
                except Exception:
                    buttons = []
            else:
                buttons = []

            context.user_data["editing_published"] = {
                "channel_id": channel_id,
                "message_id": int(msg_id),
                "text": text or "",
                "photos": photos,
                "buttons": buttons,
            }

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати текст", callback_data="ep_edit_text"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Назад до списку", callback_data="ep_back_to_list"
                    )
                ],
                [InlineKeyboardButton("❌ Закрити", callback_data="ep_cancel")],
            ]
            await query.message.reply_text(
                "📝 Виберіть, що редагувати у вже опублікованому пості:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return EDIT_PUBLISHED_MENU

        elif action == "deletepublished":
            # show confirmation dialog
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Так, видалити",
                        callback_data=f"dp_confirm_{msg_id}_{channel_id}",
                    )
                ],
                [InlineKeyboardButton("❌ Скасувати", callback_data="dp_cancel")],
            ]
            await query.edit_message_text(
                f"⚠️ Ви впевнені, що хочете видалити пост з каналу @{channel_id}?\n\n"
                "Цю дію неможливо скасувати!",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return DELETE_PUBLISHED_CONFIRM
        return ConversationHandler.END

    async def edit_published_menu_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        from telegram.ext import ConversationHandler

        query = update.callback_query
        await query.answer()

    async def handle_edit_callbacks(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle edit callbacks (ep_edit_text, ep_edit_photos, etc.)."""
        query = update.callback_query
        data = query.data
        
        if data == "ep_edit_text":
            return await self.edit_published_text_handler(update, context)
        elif data == "ep_back_to_list":
            return await self.back_to_posts_list(update, context)
        else:
            context.user_data.pop("editing_published", None)
            await query.edit_message_text("✅ Редагування завершено.")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END

    async def edit_published_text_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show current text and ask for new text."""
        query = update.callback_query
        await query.answer()
        
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            await query.message.reply_text("❌ Дані редагування відсутні.")
            return EDIT_PUBLISHED_MENU
        
        current_text = pub_data.get("text", "")
        if current_text:
            await query.message.reply_text(
                f"📝 **Поточний текст:**\n\n{current_text}\n\n✏️ Надішліть новий текст:",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                "📝 Пост не має тексту.\n\n✏️ Надішліть новий текст:"
            )
        
        from config import EDIT_PUBLISHED_TEXT
        return EDIT_PUBLISHED_TEXT

    async def edit_published_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle new text input."""
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            await update.message.reply_text("❌ Дані редагування відсутні.")
            return EDIT_PUBLISHED_MENU
        
        new_text = update.message.text or ""
        
        # Convert entities to HTML tags to preserve formatting
        if update.message.entities:
            from utils import entities_to_html
            new_text = entities_to_html(new_text, update.message.entities)
        
        # Update data
        pub_data["text"] = new_text
        context.user_data["editing_published"] = pub_data
        
        # Try to update in database
        try:
            from database import update_published_post
            update_published_post(
                pub_data["channel_id"],
                pub_data["message_id"],
                text=new_text,
                buttons=pub_data.get("buttons", [])
            )
            
            # Try to update the message in channel
            try:
                channel_id = pub_data["channel_id"]
                message_id = pub_data["message_id"]
                
                # Format chat_id correctly
                chat_id = channel_id
                if not channel_id.startswith("-") and not channel_id.startswith("@"):
                    chat_id = f"@{channel_id}"
                
                # Try to edit the message - first as text, then as caption
                try:
                    # Try editing as text message
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=new_text
                    )
                except Exception:
                    # If that fails, try editing as caption (for media messages)
                    await context.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=new_text
                    )
                
                await update.message.reply_text("✅ Текст оновлено в каналі!")
                
            except Exception as channel_error:
                # If can't update in channel, inform user about API limitations
                await update.message.reply_text(
                    f"⚠️ Текст збережено в базі даних, але не вдалося оновити в каналі: {channel_error}\n"
                    f"Це обмеження Telegram API - не можна редагувати текст повідомлень з медіа.\n"
                    f"Для повного оновлення видаліть пост і створіть новий."
                )
                
        except Exception as e:
            await update.message.reply_text(f"❌ Не вдалося зберегти текст: {e}")
        
        # Return to edit menu
        return await self.show_edit_menu(update, context)






    async def show_edit_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show edit menu after changes."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ Редагувати текст", callback_data="ep_edit_text"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Назад до списку", callback_data="ep_back_to_list"
                )
            ],
            [InlineKeyboardButton("❌ Закрити", callback_data="ep_cancel")],
        ]
        
        if update.message:
            await update.message.reply_text(
                "📝 Що редагуємо далі?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "📝 Що редагуємо далі?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return EDIT_PUBLISHED_MENU




    async def edit_published_photos(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show photo management interface for published posts."""
        query = update.callback_query
        await query.answer()
        
        # Get current post data
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            await query.message.reply_text("❌ Дані редагування відсутні.")
            return EDIT_PUBLISHED_MENU
        
        # Get existing photos
        photos = pub_data.get("photos", [])
        
        # Ensure photos is a list
        if not isinstance(photos, list):
            photos = []
        
        
        # Show photo management interface
        keyboard = create_photo_management_keyboard(photos, "published")
        await query.message.reply_text(
            "📷 *Управління фотографіями:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        from config import MANAGE_PUBLISHED_PHOTOS
        return MANAGE_PUBLISHED_PHOTOS

    async def manage_published_photos_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle photo management for published posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        pub_data = context.user_data.get("editing_published", {})
        photos = pub_data.get("photos", [])
        
        if data.startswith("photo_del_published_"):
            # delete photo
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(photos):
                deleted_photo = photos.pop(idx)
                context.user_data["editing_published"]["photos"] = photos
                await query.answer(f"Видалено фото {idx + 1}")

            # refresh keyboard
            keyboard = create_photo_management_keyboard(photos, "published")
            await query.message.reply_text(
                "📷 *Управління фотографіями:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return MANAGE_PUBLISHED_PHOTOS

        elif data == "photo_add_published":
            # prompt to add new photo
            await query.message.reply_text(
                "📷 Надішліть фото для додавання до поста."
            )
            context.user_data["adding_photo_to"] = "editing_published"
            return MANAGE_PUBLISHED_PHOTOS

        elif data == "photo_finish_published":
            # Save changes to channel
            await self.save_published_photos_changes(update, context)
            # Message will be sent by save_published_photos_changes
            return await self.show_edit_menu(update, context)

        return MANAGE_PUBLISHED_PHOTOS

    async def save_published_photos_changes(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Save photo changes to published post."""
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            return
        
        channel_id = pub_data["channel_id"]
        message_id = pub_data["message_id"]
        photos = pub_data.get("photos", [])
        
        try:
            # Update database
            from database import update_published_post
            photos_str = str(photos) if photos else None
            update_published_post(
                channel_id, 
                message_id, 
                photos=photos_str
            )
            
            # Note: We can't edit media in Telegram, so we inform user
            # that they need to delete and repost if they want to change photos
            if len(photos) != 1:
                # Multiple photos or no photos - can't edit in place
                await update.callback_query.message.reply_text(
                    "⚠️ Для зміни кількості фотографій потрібно видалити пост і створити новий. "
                    "Зміни збережено в базі даних."
                )
            else:
                # Single photo - can try to edit caption
                await update.callback_query.message.reply_text(
                    "✅ Зміни збережено в базі даних."
                )
                
        except Exception as e:
            await update.callback_query.message.reply_text(
                f"❌ Помилка при збереженні: {e}"
            )

    async def show_edit_post_interface(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show edit post interface with preview and management options."""
        query = update.callback_query
        await query.answer()
        
        # Get current post data
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            await query.message.reply_text("❌ Дані редагування відсутні.")
            return EDIT_PUBLISHED_MENU
        
        # Show current post preview
        text = pub_data.get("text", "")
        photos = pub_data.get("photos", [])
        buttons = pub_data.get("buttons", [])
        
        # Parse photos if they exist
        if photos:
            try:
                import ast
                photos = ast.literal_eval(photos) if isinstance(photos, str) else photos
            except Exception:
                photos = [photos] if photos else []
        
        # Parse buttons if they exist
        if buttons:
            try:
                import ast
                buttons = ast.literal_eval(buttons) if isinstance(buttons, str) else buttons
            except Exception:
                buttons = []
        
        # Show preview
        if photos:
            if len(photos) == 1:
                # Single photo
                await query.message.reply_photo(
                    photo=photos[0],
                    caption=text or "📷 Фото",
                    parse_mode="HTML" if text else None,
                )
            else:
                # Multiple photos - send as media group
                from telegram import InputMediaPhoto
                media = []
                for idx, fid in enumerate(photos):
                    if idx == 0:
                        media.append(InputMediaPhoto(
                            media=fid, 
                            caption=text or "📷 Фото",
                            parse_mode="HTML" if text else None
                        ))
                    else:
                        media.append(InputMediaPhoto(media=fid))
                
                sent_messages = await context.bot.send_media_group(
                    chat_id=query.message.chat_id,
                    media=media
                )
                
                # Send buttons separately for media group
                if buttons:
                    button_text = "🔗"
                    for i, button in enumerate(buttons):
                        button_text += f" [{i+1}]"
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=button_text,
                        reply_markup=create_buttons_markup(buttons),
                    )
        else:
            # Text only
            await query.message.reply_text(
                text=text or "📝 Текстовий пост",
                parse_mode="HTML" if text else None,
            )
        
        # Show management interface
        keyboard = [
            [
                InlineKeyboardButton("✏️ Редагувати текст", callback_data="ep_edit_text")
            ],
            [
                InlineKeyboardButton("✅ Зберегти зміни", callback_data="ep_save_changes"),
                InlineKeyboardButton("❌ Скасувати", callback_data="ep_cancel")
            ]
        ]
        
        await query.message.reply_text(
            "👀 **Поточний стан поста** (вище) та опції редагування:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        
        from config import EDIT_PUBLISHED_POST
        return EDIT_PUBLISHED_POST

    async def save_published_changes(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Save changes to published post."""
        query = update.callback_query
        await query.answer()
        
        pub_data = context.user_data.get("editing_published")
        if not pub_data:
            await query.message.reply_text("❌ Дані редагування відсутні.")
            return EDIT_PUBLISHED_MENU
        
        channel_id = pub_data["channel_id"]
        message_id = pub_data["message_id"]
        
        try:
            # Update database first
            from database import update_published_post
            update_published_post(
                channel_id, 
                message_id, 
                text=pub_data.get("text"),
                photos=pub_data.get("photos"),
                buttons=pub_data.get("buttons")
            )
            
            # Try to update in channel
            try:
                # Prepare chat_id
                chat_id = channel_id
                if not channel_id.startswith('@') and not channel_id.startswith('-'):
                    chat_id = f"@{channel_id}"
                
                # Update text if changed
                if "text" in pub_data:
                    await context.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=pub_data["text"],
                        parse_mode="HTML"
                    )
                
                # Update buttons if changed
                if "buttons" in pub_data:
                    buttons = pub_data["buttons"]
                    if buttons:
                        buttons_markup = create_buttons_markup(buttons)
                        await context.bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=buttons_markup,
                        )
                    else:
                        await context.bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=None,
                        )
                
                await query.message.reply_text("✅ Зміни збережено в каналі!")
                
            except Exception as channel_error:
                # If can't update in channel, at least save to database
                await query.message.reply_text(
                    f"⚠️ Зміни збережено в базі даних, але не вдалося оновити в каналі: {channel_error}\n"
                    f"Для повного оновлення видаліть пост і створіть новий."
                )
            
            # Clear editing data
            context.user_data.pop("editing_published", None)
            
        except Exception as e:
            await query.message.reply_text(f"❌ Не вдалося зберегти зміни: {e}")
        
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    async def add_single_photo_to_published_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Add a single photo when editing published post."""
        adding_to = context.user_data.get("adding_photo_to")
        if adding_to != "editing_published":
            # Not for published posts, skip this handler
            return None

        try:
            new_file_id = update.message.photo[-1].file_id
            current_photos = context.user_data.get("editing_published", {}).get("photos", [])
            current_photos.append(new_file_id)
            context.user_data["editing_published"]["photos"] = current_photos
            await update.message.reply_text("✅ Фото додано!")

            context.user_data.pop("adding_photo_to", None)

            # show updated keyboard
            keyboard = create_photo_management_keyboard(current_photos, "published")
            await update.message.reply_text(
                "📷 *Управління фотографіями:*",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Помилка при додаванні фото: {e}"
            )

        return MANAGE_PUBLISHED_PHOTOS


    async def delete_published_confirm_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """handle delete confirmation for published posts."""
        from telegram.ext import ConversationHandler

        query = update.callback_query
        await query.answer()

        if query.data == "dp_cancel":
            await query.edit_message_text("❌ Видалення скасовано.")
            return ConversationHandler.END

        elif query.data.startswith("dp_confirm_"):
            # extract message_id and channel_id from callback data
            parts = query.data.split("_")
            msg_id = parts[2]
            channel_id = parts[3]

            try:
                await context.bot.delete_message(
                    chat_id=f"@{channel_id}", message_id=int(msg_id)
                )
                await query.edit_message_text("✅ Пост видалено з каналу.")
            except Exception as e:
                await query.edit_message_text(f"❌ Не вдалося видалити пост: {e}")

        return ConversationHandler.END

    async def view_published_posts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """show list of published posts."""
        from database import get_published_posts_by_user
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        posts = get_published_posts_by_user(update.effective_user.id)
        
        if not posts:
            # Handle both message and callback query
            if update.message:
                await update.message.reply_text(
                    "📋 У вас немає опублікованих постів.",
                    reply_markup=create_main_keyboard(),
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    "📋 У вас немає опублікованих постів.",
                    reply_markup=create_main_keyboard(),
                )
            return MAIN_MENU
        
        # Send main menu buttons
        if update.message:
            await update.message.reply_text(
                "📋 **Ваші опубліковані пости:**",
                reply_markup=create_main_keyboard(),
                parse_mode="Markdown",
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "📋 **Ваші опубліковані пости:**",
                reply_markup=create_main_keyboard(),
                parse_mode="Markdown",
            )
        
        for post in posts:
            channel_id, message_id, text, photo_id, buttons = post
            
            # Parse buttons if they exist
            buttons_list = []
            if buttons:
                try:
                    import ast
                    buttons_list = ast.literal_eval(buttons)
                except Exception:
                    buttons_list = []
            
            # Create preview text - first 5 words only
            if text and text.strip():
                words = text.split()[:5]
                preview_text = " ".join(words)
                if len(text.split()) > 5:
                    preview_text += "..."
            else:
                preview_text = "📷 Фото"
            
            keyboard = [
                [
                    InlineKeyboardButton(
                        "👀 Перегляд", callback_data=f"preview_{message_id}_{channel_id}"
                    ),
                    InlineKeyboardButton(
                        "✏️ Редагувати", callback_data=f"editpublished_{message_id}_{channel_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ Видалити", callback_data=f"deletepublished_{message_id}_{channel_id}"
                    )
                ],
            ]
            
            # Handle both message and callback query
            if update.message:
                await update.message.reply_text(
                    f"📝 **@{channel_id}** (ID: {message_id})\n\n{preview_text}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    f"📝 **@{channel_id}** (ID: {message_id})\n\n{preview_text}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
        
        return VIEW_PUBLISHED_POSTS

    async def preview_published_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """show full preview of a published post."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        query = update.callback_query
        await query.answer()
        
        # Parse callback data: preview_messageId_channelId
        data = query.data.split("_", 2)
        message_id = data[1]
        channel_id = data[2]
        
        # Get post data from database
        post_data = get_published_post(channel_id, message_id)
        if not post_data:
            await query.edit_message_text("❌ Пост не знайдено.")
            return VIEW_PUBLISHED_POSTS
        
        user_id, text, photo_id, buttons = post_data
        
        # Parse buttons if they exist
        buttons_list = []
        if buttons:
            try:
                import ast
                buttons_list = ast.literal_eval(buttons)
            except Exception:
                buttons_list = []
        
        # Create full preview
        if photo_id:
            try:
                import ast
                photos = ast.literal_eval(photo_id)
            except Exception:
                photos = [photo_id]
            
            if len(photos) == 1:
                # Single photo
                await query.message.reply_photo(
                    photo=photos[0],
                    caption=text or "📷 Фото",
                    reply_markup=create_buttons_markup(buttons_list),
                    parse_mode="HTML" if text else None,
                )
            else:
                # Multiple photos - send as media group
                from telegram import InputMediaPhoto
                media = []
                for idx, fid in enumerate(photos):
                    if idx == 0:
                        media.append(InputMediaPhoto(
                            media=fid, 
                            caption=text or "📷 Фото",
                            parse_mode="HTML" if text else None
                        ))
                    else:
                        media.append(InputMediaPhoto(media=fid))
                
                sent_messages = await context.bot.send_media_group(
                    chat_id=query.message.chat_id,
                    media=media
                )
                
                # Send buttons separately for media group
                if buttons_list:
                    button_text = "🔗"
                    for i, button in enumerate(buttons_list):
                        button_text += f" [{i+1}]"
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=button_text,
                        reply_markup=create_buttons_markup(buttons_list),
                    )
        else:
            # Text only
            await query.message.reply_text(
                text=text or "📝 Текстовий пост",
                reply_markup=create_buttons_markup(buttons_list),
                parse_mode="HTML" if text else None,
            )
        
        # Show back button
        keyboard = [
            [InlineKeyboardButton("🔙 Назад до списку", callback_data="back_to_posts")]
        ]
        await query.message.reply_text(
            "👀 **Повний перегляд поста**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        
        return VIEW_PUBLISHED_POSTS

    async def back_to_posts_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """return to posts list from preview."""
        query = update.callback_query
        await query.answer()
        
        # Clear any editing data
        context.user_data.pop("editing_published", None)
        
        # Return to posts list
        return await self.view_published_posts(update, context)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """cancel operation."""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Операцію скасовано.", reply_markup=ReplyKeyboardRemove()
        )
        return await self.start(update, context)
