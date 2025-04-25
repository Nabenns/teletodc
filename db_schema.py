import aiosqlite
import asyncio
from loguru import logger

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    group_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    topic_id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL,
    topic_name TEXT NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(group_id)
);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS topic_webhook_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    webhook_id INTEGER NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id),
    FOREIGN KEY (webhook_id) REFERENCES webhooks(webhook_id),
    UNIQUE(topic_id, webhook_id)
);
"""

async def init_db(db_path: str = "config.db"):
    """Initialize the database with the schema."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

async def add_group(db_path: str, group_id: int, group_name: str):
    """Add a new group to the database."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO groups (group_id, group_name) VALUES (?, ?)",
            (group_id, group_name)
        )
        await db.commit()

async def add_topic(db_path: str, group_id: int, topic_id: int, topic_name: str):
    """Add a new topic to the database."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO topics (topic_id, group_id, topic_name) VALUES (?, ?, ?)",
            (topic_id, group_id, topic_name)
        )
        await db.commit()

async def add_webhook(db_path: str, url: str, description: str = None) -> int:
    """Add a new webhook to the database."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO webhooks (url, description) VALUES (?, ?)",
            (url, description)
        )
        await db.commit()
        return cursor.lastrowid

async def map_topic_to_webhook(db_path: str, topic_id: int, webhook_id: int):
    """Map a topic to a webhook."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO topic_webhook_mapping (topic_id, webhook_id) VALUES (?, ?)",
            (topic_id, webhook_id)
        )
        await db.commit()

async def get_webhook_for_topic(db_path: str, topic_id: int) -> str:
    """Get the webhook URL for a specific topic."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT w.url 
            FROM webhooks w 
            JOIN topic_webhook_mapping m ON w.webhook_id = m.webhook_id 
            WHERE m.topic_id = ?
            """,
            (topic_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else None

async def list_configurations(db_path: str):
    """List all configurations."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT g.group_name, t.topic_name, w.url, t.topic_id 
            FROM groups g
            JOIN topics t ON g.group_id = t.group_id
            JOIN topic_webhook_mapping m ON t.topic_id = m.topic_id
            JOIN webhooks w ON m.webhook_id = w.webhook_id
            """
        ) as cursor:
            return await cursor.fetchall()

async def delete_configuration(db_path: str, topic_id: int):
    """Delete a configuration by topic ID."""
    async with aiosqlite.connect(db_path) as db:
        # Get webhook_id for this topic
        async with db.execute(
            "SELECT webhook_id FROM topic_webhook_mapping WHERE topic_id = ?",
            (topic_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                webhook_id = result[0]
                # Delete mapping
                await db.execute("DELETE FROM topic_webhook_mapping WHERE topic_id = ?", (topic_id,))
                # Delete webhook if not used by other topics
                await db.execute("""
                    DELETE FROM webhooks 
                    WHERE webhook_id = ? 
                    AND NOT EXISTS (
                        SELECT 1 FROM topic_webhook_mapping 
                        WHERE webhook_id = ?
                    )
                """, (webhook_id, webhook_id))
                # Delete topic
                await db.execute("DELETE FROM topics WHERE topic_id = ?", (topic_id,))
                await db.commit()
                return True
        return False

if __name__ == "__main__":
    # Initialize the database when run directly
    asyncio.run(init_db()) 