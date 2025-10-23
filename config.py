import os

from dotenv import load_dotenv

# load environment variables
load_dotenv()

# hardcoded channels
HARDCODED_CHANNELS = {
    "➤ Electronics": os.getenv("FIRST_CHANNEL"),
}

# states for ConversationHandler
(
    MAIN_MENU,
    ADD_TEXT,
    ADD_PHOTO,
    ADD_BUTTONS,
    SCHEDULE_TIME,
    SELECT_CHANNEL,
    VIEW_SCHEDULED,
    EDIT_SCHEDULED_POST,
    EDIT_SCHEDULED_TEXT,
    EDIT_SCHEDULED_PHOTO,
    EDIT_SCHEDULED_BUTTONS,
    EDIT_SCHEDULED_TIME,
    EDIT_PUBLISHED_MENU,
    EDIT_PUBLISHED_TEXT,
    DELETE_PUBLISHED_CONFIRM,
    MANAGE_NEW_BUTTONS,
    MANAGE_EDIT_BUTTONS,
    EDIT_PUBLISHED_POST,
    VIEW_PUBLISHED_POSTS,
    MANAGE_NEW_PHOTOS,
    EDIT_TEXT_FROM_SCHEDULE,
    EDIT_PHOTO_FROM_SCHEDULE,
    EDIT_BUTTONS_FROM_SCHEDULE,
) = range(23)

# database settings
DATABASE_PATH = "data/bot_database.db"


# get bot token
def get_bot_token():
    return os.getenv("BOT_TOKEN")
