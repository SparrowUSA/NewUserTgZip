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
        msg_id, file_name, chat_id = await queue.get()
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Starting Stream:** `{file_name}`...")
            video_guid, error = await stream_to_bunny_vault(client, msg, file_name, BUNNY_CFG, status)
            
            if video_guid:
                link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Vaulted!**\n\n🔗 [Watch Now]({link})")
            else:
                await status.edit(f"❌ **Error:** {error}")
        except Exception:
            await client.send_message(chat_id, f"⚠️ **Crash:**\n```{traceback.format_exc()}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage)
async def zip_handler(event):
    if event.message.file and event.message.file.ext == ".zip":
        status_peek = await event.reply("🔍 **Peeking inside ZIP...**")
        files = await get_zip_filenames(client, event.message)
        
        # Filter for video files only
        videos = [f for f in files if f.lower().endswith(('.mp4', '.mkv', '.ts', '.mov'))]
        
        if not videos:
            await status_peek.edit("❌ No video files found in this ZIP.")
            return

        # Create Text Buttons (2 per row)
        btn_rows = [videos[i:i + 2] for i in range(0, len(videos), 2)]
        keyboard = [[Button.text(name, resize=True, single_use=True)] for row in btn_rows for name in row]

        await client.send_message(
            event.chat_id,
            f"✅ **Found {len(videos)} videos.** Pick one to vault:",
            buttons=keyboard
        )
        await status_peek.delete()

@client.on(events.NewMessage)
async def handle_button_click(event):
    if event.text.lower().endswith(('.mp4', '.mkv', '.ts', '.mov')):
        file_name = event.text
        await event.reply(f"🚀 **Added to Queue:** `{file_name}`", buttons=Button.clear())
        
        # Find the original ZIP message in the last 15 messages
        async for msg in client.iter_messages(event.chat_id, limit=15):
            if msg.file and msg.file.ext == ".zip":
                await queue.put((msg.id, file_name, event.chat_id))
                break

async def main():
    await client.start()
    print("Userbot is ACTIVE.")
    await client.send_message('me', "👋 **System Online.** Forward a ZIP to start.")
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
