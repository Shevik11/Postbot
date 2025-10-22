import os
import sqlite3

from config import DATABASE_PATH


def db_connect():
    """create connection to db and tables if they don't exist."""
    # create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # channels
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL UNIQUE
        )
    """
    )

    # scheduled posts
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT,
            photo_id TEXT,
            buttons TEXT, 
            publish_time DATETIME NOT NULL,
            channel_id TEXT NOT NULL,
            job_id TEXT NOT NULL UNIQUE
        )
    """
    )

    # published posts for further editing/deletion
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS published_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            text TEXT,
            photo_id TEXT,
            buttons TEXT
        )
    """
    )

    conn.commit()
    return conn


def get_scheduled_posts(user_id):
    """get list of scheduled posts of user."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, publish_time, channel_id, text FROM scheduled_posts WHERE user_id = ?",
        (user_id,),
    )
    posts = cursor.fetchall()
    conn.close()
    return posts


def get_scheduled_post_by_id(post_id):
    """get data of scheduled post by id."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT text, photo_id, buttons, publish_time, channel_id FROM scheduled_posts WHERE id = ?",
        (post_id,),
    )
    post_data = cursor.fetchone()
    conn.close()
    return post_data


def get_job_id_by_post_id(post_id):
    """get job_id of scheduled post."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT job_id FROM scheduled_posts WHERE id = ?", (post_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def save_scheduled_post(
    user_id, text, photo_id, buttons, publish_time, channel_id, job_id
):
    """save scheduled post to db."""
    import json

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scheduled_posts (user_id, text, photo_id, buttons, publish_time, channel_id, job_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            text,
            photo_id,
            json.dumps(buttons) if buttons else None,
            publish_time,
            channel_id,
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def update_scheduled_post(post_id, text, photo_id, buttons, publish_time, job_id):
    """update scheduled post in db."""
    import json

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scheduled_posts SET text=?, photo_id=?, buttons=?, publish_time=?, job_id=? WHERE id=?",
        (
            text,
            photo_id,
            json.dumps(buttons) if buttons else None,
            publish_time,
            job_id,
            post_id,
        ),
    )
    conn.commit()
    conn.close()


def delete_scheduled_post(post_id):
    """delete scheduled post from db."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()


# --- Published posts helpers ---
def save_published_post(user_id, channel_id, message_id, text, photo_id, buttons):
    """save a published post to db."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO published_posts (user_id, channel_id, message_id, text, photo_id, buttons) VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id,
            channel_id,
            message_id,
            text,
            photo_id,
            str(buttons) if buttons is not None else None,
        ),
    )
    conn.commit()
    conn.close()


def get_published_post(channel_id, message_id):
    """get published post by channel and message id."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, text, photo_id, buttons FROM published_posts WHERE channel_id = ? AND message_id = ?",
        (channel_id, message_id),
    )
    row = cursor.fetchone()
    conn.close()
    return row  # (user_id, text, photo_id, buttons)


def update_published_post(channel_id, message_id, text=None, buttons=None):
    """update fields of a published post."""
    if text is None and buttons is None:
        return
    conn = db_connect()
    cursor = conn.cursor()
    if text is not None and buttons is not None:
        cursor.execute(
            "UPDATE published_posts SET text=?, buttons=? WHERE channel_id=? AND message_id=?",
            (text, str(buttons), channel_id, message_id),
        )
    elif text is not None:
        cursor.execute(
            "UPDATE published_posts SET text=? WHERE channel_id=? AND message_id=?",
            (text, channel_id, message_id),
        )
    else:
        cursor.execute(
            "UPDATE published_posts SET buttons=? WHERE channel_id=? AND message_id=?",
            (str(buttons), channel_id, message_id),
        )
    conn.commit()
    conn.close()
