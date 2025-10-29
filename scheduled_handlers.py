import logging
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

from config import (
    EDIT_SCHEDULED_POST,
    EDIT_SCHEDULED_TEXT,
    EDIT_SCHEDULED_PHOTO,
    EDIT_SCHEDULED_BUTTONS,
    EDIT_SCHEDULED_TIME,
    MAIN_MENU,
    VIEW_SCHEDULED,
)
from database import (
    delete_scheduled_post,
    get_job_id_by_post_id,
    get_scheduled_post_by_id,
    get_scheduled_posts,
    update_scheduled_post,
)
from handlers import PostHandlers
from telegramcalendar import create_calendar, process_calendar_selection
from utils import (
    cancel_keyboard,
    create_button_management_keyboard,
    create_edit_menu_keyboard,
    create_layout_keyboard,
    create_photo_management_keyboard,
    create_main_keyboard,
    entities_to_html,
    parse_buttons,
    photo_management_keyboard,
    photo_selection_keyboard,
    skip_keyboard,
)

logger = logging.getLogger(__name__)


class ScheduledPostHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.post_handlers = PostHandlers(bot_instance)

    # --- MANAGE SCHEDULED POSTS ---
    async def view_scheduled_posts(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        posts = get_scheduled_posts(update.effective_user.id)

        if not posts:
            await update.message.reply_text("📅 У вас немає запланованих постів.")
            return MAIN_MENU

        for post in posts:
            post_id, time, channel, text = post
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати", callback_data=f"edit_scheduled_{post_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬆️ Опублікувати зараз", callback_data=f"publish_now_{post_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ Видалити пост", callback_data=f"cancel_scheduled_{post_id}"
                    )
                ],
            ]
            await update.message.reply_text(
                f"🕒 **{time}** -> **{channel}**\n\n{text[:200]}...",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
        return VIEW_SCHEDULED

    async def edit_scheduled_post_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """start editing scheduled post."""
        query = update.callback_query
        await query.answer()
        post_id = int(query.data.split("_")[-1])

        context.user_data["editing_post_id"] = post_id

        post_data = get_scheduled_post_by_id(post_id)

        if not post_data:
            await query.edit_message_text("❌ Post not found.")
            return VIEW_SCHEDULED

        text, photo_id, buttons, publish_time, channel_id, layout = post_data

        photos = []
        if photo_id:
            try:
                photos = eval(photo_id) if photo_id.startswith("[") else [photo_id]
            except Exception:
                photos = [photo_id]
        parsed_buttons = []
        if buttons:
            try:
                import json

                parsed_buttons = json.loads(buttons) if buttons else []
            except Exception as e:
                logger.warning(f"Failed to parse buttons: {e}, buttons: {buttons}")
                parsed_buttons = []

        context.user_data["editing_post"] = {
            "text": text,
            "photos": photos,
            "buttons": parsed_buttons,
            "time": datetime.fromisoformat(publish_time),
            "channel_id": channel_id,
        }

        await query.edit_message_text(
            "✏️ **РЕДАГУВАННЯ ПОСТА**\n\n"
            f"**Текст:** {text[:100]}{'...' if len(text) > 100 else ''}\n"
            f"**Фото:** {'✅' if photos else '❌'}\n"
            f"**Кнопки:** {len(parsed_buttons)}\n"
            f"**Час публікації:** {publish_time}\n"
            f"**Канал:** {channel_id}\n\n"
            "Що хочете редагувати?",
            reply_markup=create_edit_menu_keyboard(),
            parse_mode="Markdown",
        )
        return EDIT_SCHEDULED_POST

    async def cancel_scheduled_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        post_id = int(query.data.split("_")[-1])

        job_id = get_job_id_by_post_id(post_id)
        if job_id:
            try:
                self.bot.scheduler.remove_job(job_id)
            except:
                pass  # Job may not exist
            delete_scheduled_post(post_id)
            await query.edit_message_text("✅ Публікацію скасовано.")

            await self.show_scheduled_posts_after_callback(update, context)
        else:
            await query.edit_message_text("❌ Post not found.")
        return VIEW_SCHEDULED

    async def publish_now_scheduled_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Publish scheduled post immediately."""
        query = update.callback_query
        await query.answer()
        post_id = int(query.data.split("_")[-1])

        post_data = get_scheduled_post_by_id(post_id)

        if not post_data:
            await query.edit_message_text("❌ Post not found.")
            return VIEW_SCHEDULED

        text, photo_id, buttons, publish_time, channel_id, layout = post_data

        photos = []
        if photo_id:
            try:
                photos = eval(photo_id) if photo_id.startswith("[") else [photo_id]
            except Exception:
                photos = [photo_id]

        parsed_buttons = []
        if buttons:
            try:
                import json

                parsed_buttons = json.loads(buttons) if buttons else []
            except Exception as e:
                logger.warning(f"Failed to parse buttons: {e}, buttons: {buttons}")
                parsed_buttons = []

        post_data_dict = {"text": text, "photos": photos, "buttons": parsed_buttons, "layout": layout or "photo_top"}

        await self.post_handlers.send_post_job(
            channel_id, post_data_dict, update.effective_user.id, context
        )

        job_id = get_job_id_by_post_id(post_id)
        if job_id:
            try:
                self.bot.scheduler.remove_job(job_id)
            except:
                pass  # Job may not exist
        delete_scheduled_post(post_id)

        await query.edit_message_text("✅ Пост опубліковано зараз!")

        await self.show_scheduled_posts_after_callback(update, context)
        return VIEW_SCHEDULED

    # --- EDIT SCHEDULED POSTS ---
    async def edit_post_menu_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """edit post menu handler."""
        query = update.callback_query
        await query.answer()

        if query.data == "edit_text":
            await query.edit_message_text("✏️ Send new text for post:")
            return EDIT_SCHEDULED_TEXT
        elif query.data == "edit_photo":
            return await self.edit_scheduled_photo(update, context)
        elif query.data == "edit_buttons":
            return await self.edit_scheduled_buttons(update, context)
        elif query.data == "edit_layout":
            return await self.edit_scheduled_layout(update, context)
        elif query.data == "edit_time":
            cal = create_calendar()
            await query.message.reply_text(
                "🕒 Оберіть нову дату публікації:", reply_markup=cal
            )
            return EDIT_SCHEDULED_TIME
        elif query.data == "preview_edit":
            return await self.preview_edit_post(update, context)
        elif query.data == "save_edit":
            return await self.save_scheduled_post_edit(update, context)
        elif query.data == "cancel_edit":
            context.user_data.pop("editing_post", None)
            context.user_data.pop("editing_post_id", None)
            await query.edit_message_text("❌ Editing canceled.")

            await self.show_scheduled_posts_after_callback(update, context)
            return VIEW_SCHEDULED

        return EDIT_SCHEDULED_POST

    async def edit_scheduled_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """edit scheduled post text."""
        text = update.message.text

        if update.message.entities:
            text = entities_to_html(text, update.message.entities)

        context.user_data["editing_post"]["text"] = text

        await update.message.reply_text("✅ Текст оновлено!")
        return await self.show_edit_menu(update, context)

    async def edit_scheduled_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """edit scheduled post photos (show management interface)."""
        query = update.callback_query
        await query.answer()
        
        editing_post = context.user_data.get("editing_post", {})
        photos = editing_post.get("photos") or []

        if not photos:
            await query.message.reply_text(
                "📸 *Редагування фото*\n\n"
                "У цьому пості немає фото. Надішліть фото або натисніть 'Пропустити фото'.",
                reply_markup=photo_selection_keyboard(),
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text(
                f"📸 *Редагування фото*\n\n",
                reply_markup=create_photo_management_keyboard(photos, "scheduled"),
                parse_mode="Markdown",
            )
        return EDIT_SCHEDULED_PHOTO

    async def edit_scheduled_buttons(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """edit scheduled post buttons (show management interface)."""
        query = update.callback_query
        await query.answer()
        
        editing_post = context.user_data.get("editing_post", {})
        buttons = editing_post.get("buttons", [])

        # Show button management interface
        keyboard = create_button_management_keyboard(buttons, "scheduled")
        
        await query.message.reply_text(
            f"🔘 *Редагування кнопок*\n\n",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        
        return EDIT_SCHEDULED_BUTTONS

    async def manage_scheduled_photos_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle photo management for scheduled posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        editing_post = context.user_data.get("editing_post", {})
        photos = editing_post.get("photos", [])

        if data.startswith("photo_del_scheduled_"):
            # delete photo
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(photos):
                deleted_photo = photos.pop(idx)
                editing_post["photos"] = photos
                context.user_data["editing_post"] = editing_post
                await query.answer(f"Видалено фото {idx + 1}")

            # refresh keyboard
            keyboard = create_photo_management_keyboard(photos, "scheduled")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return EDIT_SCHEDULED_PHOTO

        elif data == "photo_add_scheduled":
            # prompt to add new photo
            await query.message.reply_text(
                "📷 Надішліть нове фото:",
            )
            return EDIT_SCHEDULED_PHOTO

        elif data == "photo_finish_scheduled":
            # finish and return to edit menu
            await query.message.reply_text("✅ Фото оновлено!")
            return await self.show_edit_menu(update, context)

        return EDIT_SCHEDULED_PHOTO

    async def manage_scheduled_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle button management for scheduled posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        editing_post = context.user_data.get("editing_post", {})
        buttons = editing_post.get("buttons", [])

        if data.startswith("btn_del_scheduled_"):
            # delete button
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(buttons):
                deleted_btn = buttons.pop(idx)
                editing_post["buttons"] = buttons
                context.user_data["editing_post"] = editing_post
                await query.answer(f"Видалено: {deleted_btn['text']}")

            # refresh keyboard
            keyboard = create_button_management_keyboard(buttons, "scheduled")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return EDIT_SCHEDULED_BUTTONS

        elif data == "btn_add_scheduled":
            # prompt to add new button
            await query.message.reply_text(
                "Надішліть кнопку у форматі: `Назва кнопки - https://example.com`",
                parse_mode="Markdown",
            )
            context.user_data["adding_button_to"] = "editing_post"
            return EDIT_SCHEDULED_BUTTONS

        elif data == "btn_finish_scheduled":
            # finish and return to edit menu
            await query.message.reply_text("✅ Кнопки оновлено!")
            return await self.show_edit_menu(update, context)

        return EDIT_SCHEDULED_BUTTONS

    async def add_button_to_edit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Add a single button when editing scheduled post."""
        adding_to = context.user_data.get("adding_button_to")
        if adding_to != "editing_post":
            # Not for editing post, skip this handler
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

                # Show updated button management interface
                updated_buttons = context.user_data[adding_to]["buttons"]
                keyboard = create_button_management_keyboard(updated_buttons, "scheduled")
                
                await update.message.reply_text(
                    f"🔘 *Редагування кнопок*\n\n",
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )

            context.user_data.pop("adding_button_to", None)

        except Exception as e:
            await update.message.reply_text(
                f"❌ Помилка при додаванні кнопки: {str(e)}"
            )

        return EDIT_SCHEDULED_BUTTONS

    async def add_photo_to_edit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """add new photo to editing post."""
        editing_post = context.user_data.get("editing_post", {})
        photos = editing_post.get("photos") or []
        photos.append(update.message.photo[-1].file_id)
        editing_post["photos"] = photos
        context.user_data["editing_post"] = editing_post

        await update.message.reply_text(
            f"✅ Фото додано!",
            reply_markup=photo_management_keyboard(photos),
        )
        return EDIT_SCHEDULED_PHOTO

    async def delete_photo_from_edit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """delete photo from editing post."""
        message_text = update.message.text
        # Extract photo number from delete button text
        photo_num = int(message_text.split()[-1]) - 1  # Convert to 0-based index

        editing_post = context.user_data.get("editing_post", {})
        photos = editing_post.get("photos") or []

        if 0 <= photo_num < len(photos):
            deleted_photo = photos.pop(photo_num)
            editing_post["photos"] = photos
            context.user_data["editing_post"] = editing_post

            await update.message.reply_text(
                f"✅ Фото видалено!",
                reply_markup=photo_management_keyboard(photos),
            )
        else:
            await update.message.reply_text("❌ Невірний номер фото!")

        return EDIT_SCHEDULED_PHOTO

    async def prompt_add_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """prompt user to add new photo."""
        await update.message.reply_text(
            "📸 Надішліть нове фото:", reply_markup=cancel_keyboard()
        )
        return EDIT_SCHEDULED_PHOTO

    async def preview_edit_photos(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """preview photos being edited."""
        editing_post = context.user_data.get("editing_post", {})
        photos = editing_post.get("photos", [])

        if not photos:
            await update.message.reply_text("❌ Немає фото для перегляду!")
            return EDIT_SCHEDULED_PHOTO

        try:
            if len(photos) == 1:
                await update.effective_message.reply_photo(
                    photo=photos[0], caption=f"📸 Попередній перегляд фото (1 з 1)"
                )
            else:
                # Send media group for multiple photos
                from telegram import InputMediaPhoto

                media = []
                for idx, fid in enumerate(photos):
                    if idx == 0:
                        media.append(
                            InputMediaPhoto(
                                media=fid,
                                caption=f"📸 Попередній перегляд фото (1-{len(photos)} з {len(photos)})",
                            )
                        )
                    else:
                        media.append(InputMediaPhoto(media=fid))

                await update.effective_message.reply_media_group(media)
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка при показі фото: {e}")

        return EDIT_SCHEDULED_PHOTO

    async def delete_all_photos_edit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """delete all photos from editing post."""
        editing_post = context.user_data.get("editing_post", {})
        photos_count = len(editing_post.get("photos", []))
        editing_post["photos"] = []  # Remove all photos
        context.user_data["editing_post"] = editing_post

        await update.message.reply_text(
            f"✅ Всі фото видалено! Було видалено: {photos_count} шт.\n\n"
            f"Натисніть ➕ щоб додати нове фото\n"
            f"Натисніть ✅ коли закінчите",
            reply_markup=photo_management_keyboard([]),
        )
        return EDIT_SCHEDULED_PHOTO

    async def skip_photo_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """skip photo editing."""
        editing_post = context.user_data.get("editing_post", {})
        editing_post["photos"] = []  # Remove all photos
        context.user_data["editing_post"] = editing_post

        await update.message.reply_text("✅ Фото пропущено!")
        return await self.show_edit_menu(update, context)

    async def finish_edit_photo_selection_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """finish editing photo selection and return to edit menu."""
        await update.message.reply_text("✅ Фото оновлено!")
        return await self.show_edit_menu(update, context)





        return MANAGE_EDIT_BUTTONS

    async def preview_edit_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show preview of edited post."""
        # Debug logging
        editing_post = context.user_data.get("editing_post", {})
        logger.info(f"Preview editing_post data: {editing_post}")
        logger.info(f"Preview buttons: {editing_post.get('buttons', [])}")
        logger.info(f"Preview buttons type: {type(editing_post.get('buttons', []))}")
        logger.info(f"Preview buttons length: {len(editing_post.get('buttons', []))}")

        # Create buttons markup to check
        from utils import create_buttons_markup

        buttons_markup = create_buttons_markup(editing_post.get("buttons", []))
        logger.info(f"Created buttons markup: {buttons_markup}")

        await self.post_handlers.preview_post(update, context, "editing_post")

        # Show edit menu again after preview
        await update.callback_query.message.reply_text(
            "✏️ **РЕДАГУВАННЯ ПОСТА**\n\n" "Що хочете редагувати далі?",
            reply_markup=create_edit_menu_keyboard(),
            parse_mode="Markdown",
        )
        return EDIT_SCHEDULED_POST

    async def edit_scheduled_time(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """edit scheduled post time using calendar for date and text for time."""
        try:
            date_obj = context.user_data.get("editing_selected_date")
            if not date_obj:
                await update.message.reply_text("Спочатку оберіть дату у календарі.")
                return EDIT_SCHEDULED_TIME
            time_obj = datetime.strptime(update.message.text, "%H:%M").time()
            new_dt = datetime.combine(date_obj, time_obj)
            if new_dt < datetime.now():
                await update.message.reply_text(
                    "Цей час вже минув. Введіть майбутню дату/час."
                )
                return EDIT_SCHEDULED_TIME
            context.user_data["editing_post"]["time"] = new_dt
            context.user_data.pop("editing_selected_date", None)
            await update.message.reply_text("✅ Час публікації оновлено!")
            return await self.show_edit_menu(update, context)
        except ValueError:
            await update.message.reply_text(
                "Невірний формат часу. Надішліть у форматі ГГ:ХХ, напр. 23:59"
            )
            return EDIT_SCHEDULED_TIME

    async def edit_calendar_callback_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()
        result, key, date = process_calendar_selection(context.bot, update)
        if result and date:
            context.user_data["editing_selected_date"] = date
            await query.message.reply_text(
                "Оберіть час у форматі ГГ:ХХ (наприклад 23:59)"
            )
        else:
            await query.edit_message_reply_markup(reply_markup=key)
            return EDIT_SCHEDULED_TIME

    async def show_edit_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """show edit menu after changes."""
        editing_post = context.user_data.get("editing_post", {})

        text = editing_post.get("text", "")
        photos = editing_post.get("photos", [])
        buttons = editing_post.get("buttons", [])
        time = editing_post.get("time", "")
        channel_id = editing_post.get("channel_id", "")

        await update.effective_message.reply_text(
            "✏️ **РЕДАГУВАННЯ ПОСТА**\n\n"
            f"**Текст:** {text[:100]}{'...' if len(text) > 100 else ''}\n"
            f"**Фото:** {'✅' if photos else '❌'}\n"
            f"**Кнопки:** {len(buttons)}\n"
            f"**Час публікації:** {time}\n"
            f"**Канал:** {channel_id}\n\n"
            "Що хочете редагувати?",
            reply_markup=create_edit_menu_keyboard(),
            parse_mode="Markdown",
        )
        return EDIT_SCHEDULED_POST

    async def save_scheduled_post_edit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """save scheduled post edit."""
        query = update.callback_query
        await query.answer()

        post_id = context.user_data.get("editing_post_id")
        editing_post = context.user_data.get("editing_post")

        if not post_id or not editing_post:
            await query.edit_message_text(
                "❌ Помилка: дані для редагування не знайдено."
            )
            return VIEW_SCHEDULED

        # first remove old job from scheduler
        old_job_id = get_job_id_by_post_id(post_id)
        if old_job_id:
            try:
                self.bot.scheduler.remove_job(old_job_id)
            except:
                pass  # Job may not exist

        # add new job with updated time
        new_job_id = (
            f"post_{update.effective_user.id}_{int(datetime.now().timestamp())}"
        )
        self.bot.scheduler.add_job(
            self.post_handlers.send_post_job,
            "date",
            run_date=editing_post["time"],
            args=[editing_post["channel_id"], editing_post, update.effective_user.id],
            id=new_job_id,
        )

        # update record in db
        update_scheduled_post(
            post_id,
            editing_post["text"],
            (
                str(editing_post.get("photos", []))
                if editing_post.get("photos") is not None
                else None
            ),
            editing_post["buttons"],
            editing_post["time"],
            new_job_id,
        )

        # clear editing data
        context.user_data.pop("editing_post", None)
        context.user_data.pop("editing_post_id", None)

        await query.edit_message_text("✅ Пост успішно оновлено!")

        # show updated list of scheduled posts
        await self.show_scheduled_posts_after_callback(update, context)
        return VIEW_SCHEDULED

    async def show_scheduled_posts_after_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """show list of scheduled posts after callback query."""
        posts = get_scheduled_posts(update.effective_user.id)

        if not posts:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="📅 У вас немає запланованих постів.",
                reply_markup=create_main_keyboard(),
            )
            return

        # Send main menu buttons
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="📅 **Ваші відкладені пости:**",
            reply_markup=create_main_keyboard(),
            parse_mode="Markdown",
        )

        for post in posts:
            post_id, time, channel, text = post
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати", callback_data=f"edit_scheduled_{post_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬆️ Опублікувати зараз", callback_data=f"publish_now_{post_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ Видалити пост", callback_data=f"cancel_scheduled_{post_id}"
                    )
                ],
            ]
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=f"🕒 **{time}** -> **{channel}**\n\n{text[:200]}...",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )

    async def edit_scheduled_layout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Edit scheduled post layout."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🖼️ Оберіть розташування фото:",
            reply_markup=create_layout_keyboard()
        )
        return EDIT_SCHEDULED_POST

    async def handle_scheduled_layout_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle scheduled post layout choice selection."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "layout_photo_top":
            context.user_data["editing_post"]["layout"] = "photo_top"
            await query.edit_message_text("✅ Розташування: фото зверху")
        elif data == "layout_photo_bottom":
            context.user_data["editing_post"]["layout"] = "photo_bottom"
            await query.edit_message_text("✅ Розташування: фото знизу")
        elif data == "back_to_schedule":
            await query.edit_message_text(
                "📝 **РЕДАГУВАННЯ ПОСТА**\n\nЩо хочете редагувати далі?",
                reply_markup=create_edit_menu_keyboard()
            )
            return EDIT_SCHEDULED_POST
        
        # Show edit menu
        await query.message.reply_text(
            "📝 **РЕДАГУВАННЯ ПОСТА**\n\nЩо хочете редагувати далі?",
            reply_markup=create_edit_menu_keyboard()
        )
        return EDIT_SCHEDULED_POST
