import os

from dotenv import load_dotenv

# load environment variables
load_dotenv()

# hardcoded channels
HARDCODED_CHANNELS = {
    "➤ Electronics": os.getenv("FIRST_CHANNEL"),
    "➤ FECT": os.getenv("SECOND_CHANNEL"),
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
    EDIT_PUBLISHED_BUTTONS,
    DELETE_PUBLISHED_CONFIRM,
    MANAGE_NEW_BUTTONS,
    MANAGE_EDIT_BUTTONS,
    MANAGE_PUBLISHED_BUTTONS,
) = range(19)

# database settings
DATABASE_PATH = "data/bot_database.db"


# get bot token
def get_bot_token():
    return os.getenv("BOT_TOKEN")
