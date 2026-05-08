import os
import asyncio
import gc
import traceback
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession 
from dotenv import load_dotenv
from utils import stream_to_bunny_vault, get_zip_filenames

load_dotenv()

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
LOG_CHANNEL = -1003705284928  # <--- REPLACE WITH YOUR ACTUAL CHANNEL ID
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

async def send_log(text):
    """Helper to send logs to your private channel."""
    try:
        # We use 'silent=True' so your phone doesn't buzz for every log
        await client.send_message(LOG_CHANNEL, f"📝 **LOG:**\n{text}", silent=True)
    except Exception as e:
        print(f"Failed to send log to channel: {e}")

async def worker():
    while True:
        msg_id, file_path, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Processing:** `{file_path.split('/')[-1]}`...")
            
            await send_log(f"🚀 Starting upload: `{file_path}`\nTarget: Bunny Library {BUNNY_CFG['LIBRARY_ID']}")
            
            video_guid, error = await stream_to_bunny_vault(client, msg, file_path, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted!**\n\n🔗 [Watch Now]({link})")
                await send_log(f"✅ SUCCESS: `{file_path}`\nGUID: `{video_guid}`")
            else:
                await status.edit(f"❌ **Error:** {error}")
                await send_log(f"❌ UPLOAD ERROR: `{file_path}`\nReason: {error}")
        except Exception:
            err_msg = traceback.format_exc()
            print(f"WORKER CRASH: {err_msg}")
            await send_log(f"⚠️ WORKER CRASH:\n```{err_msg}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def debug_handler(event):
    if event.message.file and event.message.file.ext == ".zip":
        sender = await event.get_sender()
        name = getattr(sender, 'first_name', 'System')
        await send_log(f"📦 ZIP Detected from **{name}**\nFile: `{event.message.file.name}`")
        await zip_handler(event)

# ... (Keep your zip_handler and handle_button_click logic here) ...

async def main():
    await client.start()
    me = await client.get_me()
    print(f"✅ Userbot is ACTIVE as @{me.username}")
    
    # Alert the log channel that the bot is online
    await send_log(f"🟢 **Bot Online**\nAccount: @{me.username}\nStatus: Listening for ZIPs...")
    
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
