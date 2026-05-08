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
LOG_CHANNEL = -1003705284928
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

async def send_log(text):
    if not LOG_CHANNEL: return
    try: await client.send_message(LOG_CHANNEL, f"📝 **SYSTEM LOG**\n\n{text}", silent=True)
    except: pass

async def zip_handler(event):
    """Scans ZIP and sends a split text list of all files."""
    try:
        status_peek = await event.reply("🔍 **Scanning ZIP (Text List Mode)...**")
        all_paths = await get_zip_filenames(client, event.message)
        
        if not all_paths:
            await status_peek.edit("❌ ZIP is empty or unreadable.")
            return

        files_only = [f for f in all_paths if not f.endswith('/')]
        if not files_only:
            await status_peek.edit("❌ No files found inside.")
            return

        # Prepare the list message
        header = f"📦 **Archive Contents ({len(files_only)} items):**\n"
        header += "━━━━━━━━━━━━━━━━━━━━\n"
        header += "👉 *Copy & Paste the exact name of the file you want to vault:*\n\n"
        
        full_list = ""
        for i, file_path in enumerate(files_only, 1):
            full_list += f"`{file_path}`\n\n"

        # Telegram limit is 4096 characters per message
        # We split the list into chunks of 3500 to stay safe
        limit = 3500
        parts = [full_list[i:i+limit] for i in range(0, len(full_list), limit)]

        await status_peek.delete()
        
        # Send the first part with the header
        await event.respond(header + parts[0])
        
        # Send subsequent parts if they exist
        for part in parts[1:]:
            await event.respond(part)

    except Exception as e:
        await send_log(f"⚠️ **Zip List Error:**\n```{traceback.format_exc()}```")

async def worker():
    while True:
        msg_id, file_path, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Processing:** `{file_path.split('/')[-1]}`...")
            
            await send_log(f"🚀 **Vaulting:** `{file_path}`")
            video_guid, error = await stream_to_bunny_vault(client, msg, file_path, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted!**\n\n🔗 [Watch Now]({link})")
                await send_log(f"✅ **Success:** `{file_path}`\n🔗 {link}")
            else:
                await status.edit(f"❌ **Error:** {error}")
                await send_log(f"❌ **Failed:** `{file_path}`\nReason: {error}")
        except Exception:
            await send_log(f"⚠️ **Worker Error:**\n```{traceback.format_exc()}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def main_handler(event):
    # 1. Detect ZIP
    if event.message.file and event.message.file.ext == ".zip":
        await zip_handler(event)
        return

    # 2. Detect Paste (Match any string that looks like a file path from the list)
    # We ignore commands (starting with /)
    if not event.text.startswith('/') and len(event.text) > 3:
        target_path = event.text.strip().strip('`') # Clean backticks if user copied them
        
        # Search for the original ZIP in the last 50 messages
        async for msg in client.iter_messages(event.chat_id, limit=50):
            if msg.file and msg.file.ext == ".zip":
                await event.reply(f"📥 **Added to Queue:** `{target_path.split('/')[-1]}`")
                await queue.put((msg.id, target_path, event.chat_id))
                return

async def main():
    await client.start()
    print("✅ Userbot is ACTIVE.")
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
