import ast

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from config import (
    DELETE_PUBLISHED_CONFIRM,
    EDIT_PUBLISHED_BUTTONS,
    EDIT_PUBLISHED_MENU,
    EDIT_PUBLISHED_TEXT,
    MAIN_MENU,
    MANAGE_PUBLISHED_BUTTONS,
)
from database import get_published_post, update_published_post
from handlers import PostHandlers
from scheduled_handlers import ScheduledPostHandlers
from utils import (
    clean_unsupported_formatting,
    create_button_management_keyboard,
    create_buttons_markup,
    create_main_keyboard,
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
        return MAIN_MENU

    async def edit_delete_published_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """handler for editing/deleting published posts."""
        from telegram.ext import ConversationHandler

        query = update.callback_query
        await query.answer()
        action, msg_id, channel_id = query.data.split("_")

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
                        "✏️ Редагувати кнопки", callback_data="ep_edit_buttons"
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
        data = query.data
        if data == "ep_edit_text":
            await query.edit_message_text(
                "✏️ Надішліть новий текст для поста (підтримуються Markdown/HTML)."
            )
            return EDIT_PUBLISHED_TEXT
        elif data == "ep_edit_buttons":
            await query.edit_message_text(
                "✏️ Надішліть кнопки у форматі: `Назва кнопки - https://example.com`\n"
                "Кожна кнопка з нового рядка. Надішліть 'Пропустити' щоб прибрати всі.",
                parse_mode="Markdown",
            )
            return EDIT_PUBLISHED_BUTTONS
        else:
            context.user_data.pop("editing_published", None)
            await query.edit_message_text("✅ Редагування завершено.")
            return ConversationHandler.END

    async def edit_published_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        from telegram.ext import ConversationHandler

        data = context.user_data.get("editing_published")
        if not data:
            await update.message.reply_text("❌ Дані редагування відсутні.")
            return ConversationHandler.END
        channel_id = data["channel_id"]
        message_id = data["message_id"]
        new_text = update.message.text or ""

        # Convert entities to HTML tags to preserve formatting
        if update.message.entities:
            new_text = entities_to_html(new_text, update.message.entities)

        # Clean unsupported formatting before sending
        clean_text = clean_unsupported_formatting(new_text)
        parse_mode = detect_parse_mode(clean_text)
        buttons_markup = create_buttons_markup(data.get("buttons"))

        try:
            if data.get("photos"):
                await context.bot.edit_message_caption(
                    chat_id=f"@{channel_id}",
                    message_id=message_id,
                    caption=clean_text,
                    parse_mode=parse_mode,
                    reply_markup=buttons_markup,
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=f"@{channel_id}",
                    message_id=message_id,
                    text=clean_text,
                    parse_mode=parse_mode,
                    reply_markup=buttons_markup,
                )
            update_published_post(channel_id, message_id, text=clean_text)
            data["text"] = clean_text
            context.user_data["editing_published"] = data
            await update.message.reply_text("✅ Текст оновлено!")
        except Exception as e:
            await update.message.reply_text(f"❌ Не вдалося оновити текст: {e}")
            return EDIT_PUBLISHED_TEXT

        # Show menu again
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("✏️ Редагувати текст", callback_data="ep_edit_text")],
            [
                InlineKeyboardButton(
                    "✏️ Редагувати кнопки", callback_data="ep_edit_buttons"
                )
            ],
            [InlineKeyboardButton("❌ Закрити", callback_data="ep_cancel")],
        ]
        await update.message.reply_text(
            "Що редагуємо далі?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_PUBLISHED_MENU

    async def edit_published_buttons(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Show button management interface for published posts."""
        data = context.user_data.get("editing_published", {})
        buttons = data.get("buttons", [])

        keyboard = create_button_management_keyboard(buttons, "published")
        await update.message.reply_text(
            "📋 *Управління кнопками:*\n\n"
            "Натисніть ❌ щоб видалити кнопку\n"
            "Натисніть ➕ щоб додати нову кнопку\n"
            "Натисніть ✅ коли закінчите",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return MANAGE_PUBLISHED_BUTTONS

    async def manage_published_buttons_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle button management for published posts."""
        query = update.callback_query
        await query.answer()

        data = query.data
        buttons = context.user_data.get("editing_published", {}).get("buttons", [])

        if data.startswith("btn_del_published_"):
            # delete button
            idx = int(data.split("_")[-1])
            if 0 <= idx < len(buttons):
                deleted_btn = buttons.pop(idx)
                context.user_data["editing_published"]["buttons"] = buttons
                await query.answer(f"Видалено: {deleted_btn['text']}")

            # refresh keyboard
            keyboard = create_button_management_keyboard(buttons, "published")
            await query.edit_message_reply_markup(reply_markup=keyboard)
            return MANAGE_PUBLISHED_BUTTONS

        elif data == "btn_add_published":
            # prompt to add new button
            await query.message.reply_text(
                "Надішліть кнопку у форматі: `Назва кнопки - https://example.com`",
                parse_mode="Markdown",
            )
            context.user_data["adding_button_to"] = "editing_published"
            return MANAGE_PUBLISHED_BUTTONS

        elif data == "btn_finish_published":
            # Save changes to published post
            from telegram.ext import ConversationHandler

            pub_data = context.user_data.get("editing_published")
            if not pub_data:
                await query.message.reply_text("❌ Дані редагування відсутні.")
                return ConversationHandler.END

            channel_id = pub_data["channel_id"]
            message_id = pub_data["message_id"]

            try:
                buttons_markup = create_buttons_markup(buttons)
                await context.bot.edit_message_reply_markup(
                    chat_id=f"@{channel_id}",
                    message_id=message_id,
                    reply_markup=buttons_markup,
                )
                update_published_post(channel_id, message_id, buttons=buttons)
                await query.message.reply_text("✅ Кнопки оновлено в каналі!")
            except Exception as e:
                await query.message.reply_text(f"❌ Не вдалося оновити кнопки: {e}")
                return MANAGE_PUBLISHED_BUTTONS

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати текст", callback_data="ep_edit_text"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✏️ Редагувати кнопки", callback_data="ep_edit_buttons"
                    )
                ],
                [InlineKeyboardButton("❌ Закрити", callback_data="ep_cancel")],
            ]
            await query.message.reply_text(
                "Що редагуємо далі?", reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return EDIT_PUBLISHED_MENU

        return MANAGE_PUBLISHED_BUTTONS

    async def add_single_button_to_published_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Add a single button when editing published post."""
        adding_to = context.user_data.get("adding_button_to")
        if adding_to != "editing_published":
            # Not for published posts, skip this handler
            return None

        try:
            buttons = parse_buttons(update.message.text)
            if buttons:
                current_buttons = context.user_data.get("editing_published", {}).get(
                    "buttons", []
                )
                current_buttons.extend(buttons)
                context.user_data["editing_published"]["buttons"] = current_buttons
                await update.message.reply_text("✅ Кнопку додано!")

            context.user_data.pop("adding_button_to", None)

            # show updated keyboard
            keyboard = create_button_management_keyboard(current_buttons, "published")
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

        return MANAGE_PUBLISHED_BUTTONS

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

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """cancel operation."""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Операцію скасовано.", reply_markup=ReplyKeyboardRemove()
        )
        return await self.start(update, context)
