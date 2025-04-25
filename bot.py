import os
import asyncio
import json
from telethon import TelegramClient, events
from telethon.tl.types import Message, MessageReplyHeader
import aiohttp
from dotenv import load_dotenv
from loguru import logger

from db_schema import (
    init_db,
    add_group,
    add_topic,
    add_webhook,
    map_topic_to_webhook,
    get_webhook_for_topic,
    list_configurations
)

# Load environment variables
load_dotenv()

# Configure logging
logger.remove()  # Remove default handler
logger.add("bot.log", rotation="500 MB", level="DEBUG", 
          format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
logger.add(lambda msg: print(msg), level="INFO", 
          format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <white>{message}</white>")

class TelegramForwarder:
    def __init__(self):
        # Telegram API credentials
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        
        if not all([self.api_id, self.api_hash, self.phone]):
            raise ValueError("Missing Telegram API credentials or phone number in .env file")
        
        self.client = TelegramClient('user_session', self.api_id, self.api_hash)
        self.db_path = "config.db"
        
    async def start(self):
        """Start the user client."""
        await init_db(self.db_path)
        
        await self.client.start(phone=self.phone)
        
        if not await self.client.is_user_authorized():
            logger.info("First time login, please check your Telegram app for the code")
            await self.client.send_code_request(self.phone)
            code = input('Enter the code you received: ')
            await self.client.sign_in(self.phone, code)
        
        # Log monitored configurations
        configs = await list_configurations(self.db_path)
        if configs:
            logger.info("🔍 Monitoring konfigurasi:")
            for group_name, topic_name, webhook_url, topic_id in configs:
                logger.info(f"📌 Grup: {group_name} | Topic: {topic_name} (ID: {topic_id})")
        else:
            logger.warning("⚠️ Belum ada konfigurasi yang ditambahkan!")
        
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            try:
                message: Message = event.message
                chat = await event.get_chat()
                sender = await event.get_sender()
                
                logger.debug(f"📨 Pesan baru diterima dari {chat.title if hasattr(chat, 'title') else 'Private Chat'}")
                logger.debug(f"💬 Isi pesan: {message.text}")
                
                if not message.is_group:
                    logger.debug("❌ Bukan pesan grup, diabaikan")
                    return
                
                logger.debug(f"👥 Grup: {chat.title} (ID: {chat.id})")
                
                # Get topic information
                topic_id = None
                if hasattr(message, 'reply_to') and isinstance(message.reply_to, MessageReplyHeader):
                    topic_id = message.reply_to.reply_to_top_id or message.reply_to.reply_to_msg_id
                
                if not topic_id:
                    logger.debug(f"❌ Pesan tidak dalam topic (Message ID: {message.id})")
                    # Log message details for debugging
                    logger.debug(f"Message details: {message}")
                    if hasattr(message, 'reply_to'):
                        logger.debug(f"Reply to: {message.reply_to}")
                    return
                
                logger.debug(f"📑 Topic ID: {topic_id}")
                
                # Get webhook URL for this topic
                webhook_url = await get_webhook_for_topic(self.db_path, topic_id)
                if not webhook_url:
                    logger.debug(f"❌ Tidak ada webhook untuk topic {topic_id}")
                    return
                
                logger.info(f"✨ Memproses pesan dari {sender.username or sender.first_name} di topic {topic_id}")
                
                # Prepare message data
                message_data = {
                    "message_id": message.id,
                    "topic_id": topic_id,
                    "chat_id": chat.id,
                    "chat_title": chat.title,
                    "from_id": sender.id if sender else None,
                    "from_username": sender.username if sender else None,
                    "text": message.text,
                    "date": message.date.isoformat(),
                    "username": sender.username if sender else "Unknown",
                    "avatar_url": f"https://cdn.discordapp.com/embed/avatars/{sender.id % 5}.png" if sender else None,
                }

                # Handle media (images, videos, etc.)
                if message.media:
                    try:
                        # Download the media file
                        file_path = await message.download_media(file="downloads/")
                        logger.info(f"📥 Media downloaded to {file_path}")
                        
                        # For Discord webhooks
                        if 'discord' in webhook_url.lower():
                            message_data["file"] = file_path
                            if message.text:
                                message_data["content"] = message.text
                            else:
                                message_data["content"] = ""  # Discord requires content field
                    except Exception as e:
                        logger.error(f"❌ Error handling media: {str(e)}")
                        logger.exception(e)
                        return
                
                await self.forward_to_webhook(webhook_url, message_data)
                
                # Clean up downloaded media
                if message.media and 'file_path' in locals():
                    try:
                        os.remove(file_path)
                        logger.debug(f"🗑️ Deleted temporary media file: {file_path}")
                    except Exception as e:
                        logger.error(f"❌ Error deleting media file: {str(e)}")
                
            except Exception as e:
                logger.error(f"❌ Error saat memproses pesan: {str(e)}")
                logger.exception(e)
    
    async def forward_to_webhook(self, webhook_url: str, message_data: dict):
        """Forward message to webhook."""
        file_handle = None
        try:
            if 'discord' in webhook_url.lower():
                # Prepare Discord webhook data with embed
                webhook_data = {
                    "username": message_data.get("username", "Unknown"),
                    "avatar_url": message_data.get("avatar_url"),
                    "embeds": [{
                        "description": message_data.get("text", ""),
                        "color": 3447003,  # Blue color
                        "author": {
                            "name": message_data.get("username", "Unknown"),
                            "icon_url": message_data.get("avatar_url")
                        },
                        "timestamp": message_data.get("date")
                    }]
                }

                # If there's a file, add it to the embed as an image
                if "file" in message_data:
                    webhook_data["embeds"][0]["image"] = {
                        "url": "attachment://image.jpg"  # This will reference the uploaded file
                    }

                # Send to Discord webhook
                async with aiohttp.ClientSession() as session:
                    if "file" in message_data:
                        # Send with media
                        try:
                            file_handle = open(message_data["file"], "rb")
                            form = aiohttp.FormData()
                            form.add_field("payload_json", json.dumps(webhook_data))
                            form.add_field("file", file_handle, filename="image.jpg")
                            async with session.post(webhook_url, data=form) as response:
                                if response.status not in [200, 204]:
                                    logger.error(f"❌ Discord webhook error: {response.status}")
                                    logger.error(await response.text())
                        finally:
                            if file_handle:
                                file_handle.close()
                    else:
                        # Send text only
                        async with session.post(webhook_url, json=webhook_data) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"❌ Discord webhook error: {response.status}")
                                logger.error(await response.text())

            else:
                # Default webhook format (e.g., for Slack)
                webhook_data = {
                    "text": message_data.get("text", ""),
                    "username": message_data.get("username", "Unknown"),
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=webhook_data) as response:
                        if response.status not in [200, 204]:
                            logger.error(f"❌ Webhook error: {response.status}")
                            logger.error(await response.text())

            logger.info(f"✅ Message forwarded to webhook successfully")

        except Exception as e:
            logger.error(f"❌ Error forwarding to webhook: {str(e)}")
            logger.exception(e)
        finally:
            if file_handle:
                try:
                    file_handle.close()
                except:
                    pass
    
    async def add_configuration(self, group_id: int, group_name: str, topic_id: int, 
                              topic_name: str, webhook_url: str, description: str = None):
        """Add a new configuration for topic forwarding."""
        try:
            await add_group(self.db_path, group_id, group_name)
            await add_topic(self.db_path, group_id, topic_id, topic_name)
            webhook_id = await add_webhook(self.db_path, webhook_url, description)
            await map_topic_to_webhook(self.db_path, topic_id, webhook_id)
            logger.info(f"✅ Konfigurasi berhasil ditambahkan untuk topic {topic_name} di grup {group_name}")
        except Exception as e:
            logger.error(f"❌ Error saat menambah konfigurasi: {str(e)}")
            raise
    
    async def run(self):
        """Run the client."""
        try:
            logger.info("🚀 Memulai Telegram client...")
            await self.start()
            logger.info("✅ Client berjalan dan siap menerima pesan...")
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Client error: {str(e)}")
            logger.exception(e)
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    forwarder = TelegramForwarder()
    asyncio.run(forwarder.run()) 