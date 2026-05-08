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

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

async def worker():
    while True:
        msg_id, file_path, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Processing:** `{file_path.split('/')[-1]}`...")
            
            # Stream the specific path (even if it's deep in a folder)
            video_guid, error = await stream_to_bunny_vault(client, msg, file_path, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted!**\n\n🔗 [Watch Now]({link})")
            else:
                await status.edit(f"❌ **Error:** {error}")
        except Exception:
            await client.send_message(chat_id, f"⚠️ **Worker Crash:**\n```{traceback.format_exc()}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage)
async def zip_handler(event):
    if event.message.file and event.message.file.ext == ".zip":
        status_peek = await event.reply("🔍 **Deep Scanning ZIP (All Folders)...**")
        
        # Returns all internal paths
        all_paths = await get_zip_filenames(client, event.message)
        
        if not all_paths:
            await status_peek.edit("❌ ZIP is empty or unreadable.")
            return

        # List EVERYTHING that isn't a folder entry itself
        files_to_show = [f for f in all_paths if not f.endswith('/')]

        if not files_to_show:
            await status_peek.edit("❌ No files found (only empty folders).")
            return

        # Build 2-column button layout
        btn_rows = []
        for i in range(0, min(len(files_to_show), 40), 2):
            row = []
            for file_path in files_to_show[i:i+2]:
                # Text buttons carry the full path for the worker to find
                row.append(Button.text(file_path, resize=True, single_use=True))
            btn_rows.append(row)

        await client.send_message(
            event.chat_id,
            f"📦 **Found {len(files_to_show)} items.**\nSelect any file to upload:",
            buttons=btn_rows
        )
        await status_peek.delete()

@client.on(events.NewMessage)
async def handle_button_click(event):
    # Detect if the text is a file from our ZIP (usually contains a dot)
    if "." in event.text:
        file_path = event.text
        await event.reply(f"🚀 **Added to Queue:** `{file_path.split('/')[-1]}`", buttons=Button.clear())
        
        async for msg in client.iter_messages(event.chat_id, limit=15):
            if msg.file and msg.file.ext == ".zip":
                await queue.put((msg.id, file_path, event.chat_id))
                break

async def main():
    await client.start()
    print("Userbot is ACTIVE.")
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
