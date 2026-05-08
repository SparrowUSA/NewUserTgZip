import os
import asyncio
import gc
import traceback
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession 
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

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
queue = asyncio.Queue()

async def worker():
    while True:
        msg_id, file_name, chat_id = await queue.get()
        try:
            # Fetch message from the specific chat it came from
            msg = await client.get_messages(chat_id, ids=msg_id)
            status = await client.send_message(chat_id, f"🛠 **Starting Stream:** `{file_name}`...")
            
            video_guid, error = await stream_to_bunny_vault(client, msg, file_name, BUNNY_CFG, status)
            
            if video_guid:
                play_link = f"https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{video_guid}"
                await status.edit(f"✅ **Upload Complete!**\n\n🔗 [Watch Lecture]({play_link})")
            else:
                await status.edit(f"❌ **Transfer Failed!**\n\n**Error Details:**\n{error}")
        except Exception:
            err_log = traceback.format_exc()
            await client.send_message(chat_id, f"⚠️ **Worker Crash!**\n```{err_log}```")
        finally:
            gc.collect()
            queue.task_done()

# REMOVED 'outgoing=True' so ANYONE'S message triggers the bot
@client.on(events.NewMessage)
async def zip_handler(event):
    # Log details to Render console to see WHO is sending
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', 'Unknown')
    print(f"DEBUG: Message from {sender_name} (ID: {event.sender_id}) in Chat: {event.chat_id}")

    if event.message.file and event.message.file.ext == ".zip":
        print(f"DEBUG: ZIP detected from {sender_name}")
        try:
            await event.reply(
                f"📂 **ZIP Detected, {sender_name}!**\nSelect the file to stream:",
                buttons=[
                    # Note: These are placeholders. You can add logic to 'peek' inside here.
                    [Button.inline("Lecture 01", "Lecture_01.mp4")],
                    [Button.inline("Lecture 02", "Lecture_02.mp4")]
                ]
            )
        except Exception as e:
            print(f"DEBUG: Failed to reply: {e}")

@client.on(events.CallbackQuery())
async def callback(event):
    file_name = event.data.decode('utf-8')
    # Pass the chat_id so the worker knows where to send the link
    await queue.put((event.message_id, file_name, event.chat_id))
    await event.answer("Added to Queue! 🕒")

async def main():
    await client.start()
    print("Userbot is ACTIVE and listening to EVERYONE.")
    
    # Startup check
    await client.send_message('me', "👋 **System Online.** Listening for ZIPs from any source.")
    
    asyncio.create_task(worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
