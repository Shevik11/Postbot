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

from config import HARDCODED_CHANNELS, MANAGE_NEW_BUTTONS
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
        photos = post_data.get("photos")
        if not photos and post_data.get("photo"):
            photos = [post_data.get("photo")]
        buttons = post_data.get("buttons", [])

        buttons_markup = create_buttons_markup(buttons)

        clean_text = clean_unsupported_formatting(text)
        parse_mode = detect_parse_mode(clean_text)
        preview_text = format_text_for_preview(text)

        warnings = get_formatting_warnings(text)

        if parse_mode == "HTML":
            prefix = "👀 <b>ПЕРЕДОГЛЯД:</b>\n\n"
        elif parse_mode == "Markdown":
            prefix = "👀 **ПЕРЕДОГЛЯД:**\n\n"
        else:
            prefix = "👀 ПЕРЕДОГЛЯД:\n\n"

        if photos:
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

        from telegram.ext import Application

        bot = (
            context.bot
            if context
            else Application.builder().token(os.getenv("BOT_TOKEN")).build().bot
        )
        buttons_markup = create_buttons_markup(post_data.get("buttons"))

        try:
            clean_channel_id = channel_id.lstrip("@")

            photos = post_data.get("photos")
            if not photos and post_data.get("photo"):
                photos = [post_data.get("photo")]

            text = post_data.get("text", "")
            clean_text = clean_unsupported_formatting(text)
            parse_mode = detect_parse_mode(clean_text)

            if photos:
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
                        for i, button in enumerate(buttons):
                            button_text += f" [{i+1}]"
                        await bot.send_message(
                            chat_id=f"@{clean_channel_id}",
                            text=button_text,
                            reply_markup=buttons_markup,
                        )
            else:
                sent_message = await bot.send_message(
                    chat_id=f"@{clean_channel_id}",
                    text=clean_text,
                    reply_markup=buttons_markup,
                    parse_mode=parse_mode,
                )
            try:
                photos_to_store = None
                if photos:
                    photos_to_store = str(photos)
                save_published_post(
                    user_id,
                    channel_id,
                    sent_message.message_id,
                    text,
                    photos_to_store,
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
                f"❌ Не вдалося надіслати пост у канал @{clean_channel_id}. Перевірте, чи бот є адміністратором з правами на публікацію.",
            )

    # --- CREATE POST ---
    async def create_post_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        context.user_data["new_post"] = {}
        await update.message.reply_text(
            "Крок 1: Надішліть текст для вашого поста.", reply_markup=cancel_keyboard()
        )
        from config import ADD_TEXT

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

        await update.message.reply_text(
            "Крок 2: Надішліть одне або кілька фото. Коли закінчите, натисніть 'Завершити вибір фото'. Або натисніть 'Пропустити фото', щоб створити пост тільки з текстом.",
            reply_markup=photo_selection_keyboard(),
        )
        from config import ADD_PHOTO

        return ADD_PHOTO

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

    async def finish_photo_selection_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}
        # ensure photos key exists
        context.user_data["new_post"].setdefault("photos", [])
        await update.message.reply_text(
            "Крок 3: Додайте кнопки з посиланнями.\n"
            "Надішліть їх у форматі: `Назва кнопки - https://example.com`\n"
            "Кожна нова кнопка з нового рядка. Якщо кнопки не потрібні, натисніть 'Пропустити'.",
            reply_markup=skip_keyboard(),
        )
        from config import ADD_BUTTONS

        return ADD_BUTTONS

    async def add_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if "new_post" not in context.user_data:
            context.user_data["new_post"] = {}

        # Show button management interface
        context.user_data["new_post"].setdefault("buttons", [])
        buttons = context.user_data["new_post"]["buttons"]

        keyboard = create_button_management_keyboard(buttons, "new")
        await update.message.reply_text(
            "📋 *Управління кнопками:*\n\n"
            "Натисніть ❌ щоб видалити кнопку\n"
            "Натисніть ➕ щоб додати нову кнопку\n"
            "Натисніть ✅ коли закінчите",
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

        context.user_data["new_post"]["photos"] = []
        await update.message.reply_text(
            "Крок 3: Додайте кнопки з посиланнями.\n"
            "Надішліть їх у форматі: `Назва кнопки - https://example.com`\n"
            "Кожна нова кнопка з нового рядка. Якщо кнопки не потрібні, натисніть 'Пропустити'.",
            reply_markup=skip_keyboard(),
        )
        from config import ADD_BUTTONS

        return ADD_BUTTONS

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
                "📋 *Управління кнопками:*\n\n"
                "Натисніть ❌ щоб видалити кнопку\n"
                "Натисніть ➕ щоб додати нову кнопку\n"
                "Натисніть ✅ коли закінчите",
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
            # serialize photos list for DB storage
            photos = post_data.get("photos")
            if not photos and post_data.get("photo"):
                photos = [post_data.get("photo")]
            save_scheduled_post(
                update.effective_user.id,
                post_data.get("text"),
                str(photos) if photos else None,
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
            await self.send_post_job(
                channel_id, post_data, update.effective_user.id, context
            )
            await query.edit_message_text(
                f"✅ Пост успішно надіслано в канал {channel_id}."
            )

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
