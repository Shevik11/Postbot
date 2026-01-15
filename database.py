import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Tuple

from config import DATABASE_PATH


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize database and create tables if they don't exist."""
    with get_db_connection() as conn:
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
                media_type TEXT,
                buttons TEXT,
                publish_time DATETIME NOT NULL,
                channel_id TEXT NOT NULL,
                job_id TEXT NOT NULL UNIQUE,
                layout TEXT DEFAULT 'photo_top'
            )
            """
        )
        
        # Add layout column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE scheduled_posts ADD COLUMN layout TEXT DEFAULT 'photo_top'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # published posts
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS published_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                text TEXT,
                photo_id TEXT,
                media_type TEXT,
                buttons TEXT
            )
            """
        )
        
        # Create index for faster queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_published_user 
            ON published_posts(user_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_published_channel_msg 
            ON published_posts(channel_id, message_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scheduled_user 
            ON scheduled_posts(user_id)
            """
        )


def get_scheduled_posts(user_id: int) -> List[Tuple]:
    """Get list of scheduled posts for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, publish_time, channel_id, text FROM scheduled_posts WHERE user_id = ? ORDER BY publish_time ASC",
            (user_id,),
        )
        return cursor.fetchall()


def get_scheduled_post_by_id(post_id: int) -> Optional[Tuple]:
    """Get data of scheduled post by id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT text, photo_id, buttons, publish_time, channel_id, layout FROM scheduled_posts WHERE id = ?",
            (post_id,),
        )
        return cursor.fetchone()


def get_job_id_by_post_id(post_id: int) -> Optional[str]:
    """Get job_id of scheduled post."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT job_id FROM scheduled_posts WHERE id = ?", (post_id,))
        result = cursor.fetchone()
        return result[0] if result else None


def save_scheduled_post(
    user_id: int,
    text: Optional[str],
    photo_id: Optional[str],
    media_type: Optional[str],
    buttons: Optional[List],
    publish_time: str,
    channel_id: str,
    job_id: str,
    layout: str = "photo_top"
) -> None:
    """Save scheduled post to db."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduled_posts (user_id, text, photo_id, media_type, buttons, publish_time, channel_id, job_id, layout) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                text,
                photo_id,
                media_type,
                json.dumps(buttons) if buttons else None,
                publish_time,
                channel_id,
                job_id,
                layout,
            ),
        )


def update_scheduled_post(
    post_id: int,
    text: Optional[str],
    photo_id: Optional[str],
    media_type: Optional[str],
    buttons: Optional[List],
    publish_time: str,
    job_id: str,
    layout: Optional[str] = None
) -> None:
    """Update scheduled post in db."""
    # Build dynamic update query
    updates = []
    values = []
    
    if text is not None:
        updates.append("text = ?")
        values.append(text)
    if photo_id is not None:
        updates.append("photo_id = ?")
        values.append(photo_id)
    if media_type is not None:
        updates.append("media_type = ?")
        values.append(media_type)
    if buttons is not None:
        updates.append("buttons = ?")
        values.append(json.dumps(buttons))
    if publish_time is not None:
        updates.append("publish_time = ?")
        values.append(publish_time)
    if job_id is not None:
        updates.append("job_id = ?")
        values.append(job_id)
    if layout is not None:
        updates.append("layout = ?")
        values.append(layout)
    
    if not updates:
        return  # Nothing to update
    
    values.append(post_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE scheduled_posts SET {', '.join(updates)} WHERE id = ?",
            values,
        )


def delete_scheduled_post(post_id: int) -> None:
    """Delete scheduled post from db."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))


def save_published_post(
    user_id: int,
    channel_id: str,
    message_id: int,
    text: Optional[str],
    photo_id: Optional[str],
    media_type: Optional[str],
    buttons: Optional[List],
) -> None:
    """Save a published post to db."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO published_posts (user_id, channel_id, message_id, text, photo_id, media_type, buttons) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                channel_id,
                message_id,
                text,
                photo_id,
                media_type,
                json.dumps(buttons) if buttons is not None else None,
            ),
        )


def get_published_post(channel_id: str, message_id: int) -> Optional[Tuple]:
    """Get published post by channel and message id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, text, photo_id, media_type, buttons FROM published_posts WHERE channel_id = ? AND message_id = ?",
            (channel_id, message_id),
        )
        return cursor.fetchone()


def update_published_post(
    channel_id: str,
    message_id: int,
    text: Optional[str] = None,
    photo_id: Optional[str] = None,
    buttons: Optional[List] = None,
) -> None:
    """Update fields of a published post."""
    # Build dynamic update query
    updates = []
    values = []
    
    if text is not None:
        updates.append("text = ?")
        values.append(text)
    if photo_id is not None:
        updates.append("photo_id = ?")
        values.append(photo_id)
    if buttons is not None:
        updates.append("buttons = ?")
        values.append(json.dumps(buttons))
    
    if not updates:
        return  # Nothing to update
    
    values.extend([channel_id, message_id])
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE published_posts SET {', '.join(updates)} WHERE channel_id = ? AND message_id = ?",
            values,
        )


def get_published_posts_by_user(user_id: int) -> List[Tuple]:
    """Get all published posts by user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT channel_id, message_id, text, photo_id, media_type, buttons FROM published_posts WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return cursor.fetchall()
