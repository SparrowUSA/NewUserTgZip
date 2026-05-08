import os
import asyncio
import gc
import traceback
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession  # <--- Essential for Render
from dotenv import load_dotenv
from utils import stream_to_bunny_vault

load_dotenv()

# Environment Variables from Render Dashboard
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

# Fix: Use StringSession so Telethon doesn't try to create a local .session file
client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

queue = asyncio.Queue()

async def worker():
    """Processes the queue one by one to keep RAM flat."""
    while True:
        msg_id, file_name = await queue.get()
        try:
            msg = await client.get_messages('me', ids=msg_id)
            status = await client.send_message('me', f"🛠 **Starting Stream:** `{file_name}`...")
            
            # Start the transfer logic
            video_guid, error = await stream_to_bunny_vault(client, msg, file_name, BUNNY_CFG, status)
            
            if video_guid:
                play_link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Upload Complete!**\n\n🔗 [Watch Lecture]({play_link})")
            else:
                await status.edit(f"❌ **Transfer Failed!**\n\n**Error Details:**\n{error}")
        except Exception:
            err_log = traceback.format_exc()
            await client.send_message('me', f"⚠️ **Worker Crash!**\n```{err_log}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage(outgoing=True))
async def zip_handler(event):
    # Detects ZIP files in your Saved Messages
    if event.message.file and event.message.file.ext == ".zip":
        await event.reply(
            "📂 **ZIP Detected.** Select the file you want to stream:",
            buttons=[
                # Update these buttons or add logic in utils to list zip contents dynamically
                [Button.inline("Lecture 01", "Lecture_01.mp4")],
                [Button.inline("Lecture 02", "Lecture_02.mp4")]
            ]
        )

@client.on(events.CallbackQuery())
async def callback(event):
    # Adds the selected file to the background queue
    file_name = event.data.decode('utf-8')
    await queue.put((event.message_id, file_name))
    await event.answer("Added to Queue! 🕒")

async def main():
    await client.start()
    
    # Send a startup notification
    await client.send_message('me', "👋 **Hello! Vault Userbot is ACTIVE on Render.**\nI am ready to process your ZIP files.")
    
    # Start the background worker
    asyncio.create_task(worker())
    
    print("Userbot is running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
