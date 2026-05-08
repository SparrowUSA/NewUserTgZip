import os, asyncio, gc, traceback
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv
from utils import stream_to_bunny_vault

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

client = TelegramClient(SESSION, API_ID, API_HASH)
queue = asyncio.Queue()

async def worker():
    while True:
        msg_id, file_name = await queue.get()
        try:
            msg = await client.get_messages('me', ids=msg_id)
            status = await client.send_message('me', f"🛠 **Starting Stream:** `{file_name}`...")
            
            video_guid, error = await stream_to_bunny_vault(client, msg, file_name, BUNNY_CFG, status)
            
            if video_guid:
                play_link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Upload Complete!**\n\n🔗 [Watch Lecture]({play_link})")
            else:
                await status.edit(f"❌ **Transfer Failed!**\n\n**Error:** {error}")
        except Exception:
            await client.send_message('me', f"⚠️ **Worker Crash!**\n```{traceback.format_exc()}```")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage(outgoing=True))
async def zip_handler(event):
    if event.message.file and event.message.file.ext == ".zip":
        await event.reply(
            "📂 **ZIP Detected.** Select file to stream:",
            buttons=[[Button.inline("Stream Video", "lecture.mp4")]] # Replace with dynamic list if needed
        )

@client.on(events.CallbackQuery())
async def callback(event):
    await queue.put((event.message_id, event.data.decode('utf-8')))
    await event.answer("Added to Queue! 🕒")

async def main():
    await client.start()
    await client.send_message('me', "👋 **Hello! Vault Userbot is ACTIVE.**\nReady for streaming.")
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
