import os
import asyncio
import gc
import traceback
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession 
from dotenv import load_dotenv
from utils import stream_to_bunny_vault, get_zip_filenames

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

# Initialize Client
client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

async def worker():
    """Background worker to process the upload queue."""
    while True:
        msg_id, file_path, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Processing:** `{file_path.split('/')[-1]}`...")
            
            video_guid, error = await stream_to_bunny_vault(client, msg, file_path, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted Successfully!**\n\n🔗 [Watch Now]({link})")
            else:
                await status.edit(f"❌ **Error:** {error}")
        except Exception:
            print(f"WORKER CRASH: {traceback.format_exc()}")
        finally:
            gc.collect()
            queue.task_done()

# GLOBAL LISTENER: Catch everything for debugging
@client.on(events.NewMessage(incoming=True, outgoing=True))
async def debug_handler(event):
    sender = await event.get_sender()
    name = getattr(sender, 'first_name', 'System/Self')
    print(f"📩 LOG: Message received from '{name}': {event.text[:50]}")

    # Check if it's a ZIP file
    if event.message.file and event.message.file.ext == ".zip":
        print(f"📦 LOG: ZIP detected: {event.message.file.name}")
        await zip_handler(event)

async def zip_handler(event):
    """Deep scans ZIP and sends the button menu."""
    try:
        status_peek = await event.reply("🔍 **Scanning ZIP folders...**")
        all_paths = await get_zip_filenames(client, event.message)
        
        if not all_paths:
            await status_peek.edit("❌ ZIP is empty or unreadable.")
            return

        # Filter out folder-only entries
        files_only = [f for f in all_paths if not f.endswith('/')]

        if not files_only:
            await status_peek.edit("❌ No files found inside.")
            return

        # Build buttons (2 columns)
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
        print(f"ZIP HANDLER ERROR: {e}")

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handle_button_click(event):
    """Detects when a file path button is pressed."""
    # Logic to identify if text is a file path button
    if "." in event.text and not event.text.startswith('/'):
        file_path = event.text
        # Search back for the original ZIP
        async for msg in client.iter_messages(event.chat_id, limit=20):
            if msg.file and msg.file.ext == ".zip":
                await event.reply(f"🚀 **Added to Queue:** `{file_path.split('/')[-1]}`", buttons=Button.clear())
                await queue.put((msg.id, file_path, event.chat_id))
                return

async def main():
    await client.start()
    me = await client.get_me()
    print(f"✅ Userbot is ACTIVE as @{me.username}")
    
    # Notify Saved Messages
    await client.send_message('me', "👋 **System Online.** Listening for ZIPs.")
    
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
