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
# REPLACE -100xxxxxxxxxx with your actual Log Channel ID
LOG_CHANNEL = -1003705284928 

BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

# --- HELPERS ---

async def send_log(text):
    """Sends logs to your private channel."""
    if not LOG_CHANNEL:
        return
    try:
        await client.send_message(LOG_CHANNEL, f"📝 **SYSTEM LOG**\n\n{text}", silent=True)
    except Exception as e:
        print(f"Log Error: {e}")

# --- CORE FUNCTIONS ---

async def zip_handler(event):
    """Deep scans ZIP and sends the button menu."""
    try:
        status_peek = await event.reply("🔍 **Scanning ZIP folders...**")
        await send_log(f"🔎 Peeking into ZIP: `{event.message.file.name}`")
        
        all_paths = await get_zip_filenames(client, event.message)
        
        if not all_paths:
            await status_peek.edit("❌ ZIP is empty or unreadable.")
            await send_log("❌ Failed to read ZIP headers.")
            return

        files_only = [f for f in all_paths if not f.endswith('/')]

        if not files_only:
            await status_peek.edit("❌ No files found inside.")
            return

        btn_rows = []
        for i in range(0, min(len(files_only), 40), 2):
            row = [Button.text(fp, resize=True, single_use=True) for fp in files_only[i:i+2]]
            btn_rows.append(row)

        await client.send_message(
            event.chat_id,
            f"📋 **Found {len(files_only)} items.**\nSelect a file to upload:",
            buttons=btn_rows
        )
        await status_peek.delete()
    except Exception as e:
        err = traceback.format_exc()
        print(f"ZIP HANDLER ERROR: {err}")
        await send_log(f"⚠️ **Zip Handler Error:**\n```{err}```")

async def worker():
    """Background worker to process the upload queue."""
    while True:
        msg_id, file_path, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Processing:** `{file_path.split('/')[-1]}`...")
            
            await send_log(f"🚀 **Starting Upload:** `{file_path}`")
            
            video_guid, error = await stream_to_bunny_vault(client, msg, file_path, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted Successfully!**\n\n🔗 [Watch Now]({link})")
                await send_log(f"✅ **Success:** `{file_path}`\n🔗 [Link]({link})")
            else:
                await status.edit(f"❌ **Error:** {error}")
                await send_log(f"❌ **Upload Failed:** `{file_path}`\nReason: {error}")
        except Exception:
            err = traceback.format_exc()
            print(f"WORKER CRASH: {err}")
            await send_log(f"⚠️ **Worker Crash:**\n```{err}```")
        finally:
            gc.collect()
            queue.task_done()

# --- EVENT HANDLERS ---

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def main_handler(event):
    # 1. Handle ZIP Files
    if event.message.file and event.message.file.ext == ".zip":
        await zip_handler(event)
        return

    # 2. Handle Button Clicks (File Paths)
    if "." in event.text and not event.text.startswith('/'):
        file_path = event.text
        async for msg in client.iter_messages(event.chat_id, limit=20):
            if msg.file and msg.file.ext == ".zip":
                await event.reply(f"🚀 **Added to Queue:** `{file_path.split('/')[-1]}`", buttons=Button.clear())
                await queue.put((msg.id, file_path, event.chat_id))
                return

async def main():
    await client.start()
    me = await client.get_me()
    print(f"✅ Userbot is ACTIVE as @{me.username}")
    await send_log(f"🟢 **Userbot Online**\nAccount: @{me.username}")
    
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
