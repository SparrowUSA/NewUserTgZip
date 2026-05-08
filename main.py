import os
import asyncio
import gc
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv
from utils import stream_to_bunny

load_dotenv()

# Environment Variables (Set these in Render Dashboard)
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BUNNY_CFG = {
    "KEY": os.getenv("BUNNY_API_KEY"),
    "ZONE": os.getenv("BUNNY_STORAGE_ZONE"),
    "URL": os.getenv("BUNNY_PULL_ZONE")
}

client = TelegramClient(SESSION, API_ID, API_HASH)
queue = asyncio.Queue()

async def worker():
    """Processes the queue one-by-one to keep RAM flat."""
    while True:
        msg_id, file_name = await queue.get()
        try:
            msg = await client.get_messages('me', ids=msg_id)
            status_msg = await client.send_message('me', f"🛠 **Streaming:** `{file_name}` to Bunny...")
            
            success = await stream_to_bunny(client, msg, file_name, BUNNY_CFG)
            
            if success:
                final_link = f"https://{BUNNY_CFG['URL']}/{file_name}"
                await status_msg.edit(f"✅ **Uploaded!**\n🔗 [Stream Link]({final_link})")
            else:
                await status_msg.edit(f"❌ Failed to transfer `{file_name}`")
        except Exception as e:
            print(f"Worker Error: {e}")
        finally:
            gc.collect()
            queue.task_done()

@client.on(events.NewMessage(outgoing=True))
async def zip_listener(event):
    if event.message.file and event.message.file.ext == ".zip":
        # For 'peeking', we'll use a placeholder button. 
        # You can expand this to list real file names from utils.
        await event.reply(
            "📂 **ZIP Detected in Saved Messages**\nSelect a file to stream to your Vault:",
            buttons=[
                [Button.inline("Stream: Lecture_01.mp4", "Lecture_01.mp4")],
                [Button.inline("Stream: Lecture_02.ts", "Lecture_02.ts")]
            ]
        )

@client.on(events.CallbackQuery())
async def callback_handler(event):
    file_to_process = event.data.decode('utf-8')
    await queue.put((event.message_id, file_to_process))
    await event.answer("Added to transfer queue! 🕒", alert=False)

async def main():
    await client.start()
    asyncio.create_task(worker())
    print("Vault Userbot is live...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
