import gc
import aiohttp
import asyncio
import traceback
import time
import threading
import queue
import requests
from stream_unzip import stream_unzip

class Progress:
    def __init__(self, client, status_msg, file_name):
        self.client = client
        self.status_msg = status_msg
        self.file_name = file_name
        self.last_update = 0

    async def update(self, current_bytes):
        now = time.time()
        if now - self.last_update > 10:
            mb = current_bytes / (1024 * 1024)
            try:
                await self.client.edit_message(
                    self.status_msg.chat_id,
                    self.status_msg.id,
                    f"🛠 **Streaming:** `{self.file_name.split('/')[-1]}`\n📤 **Transferred:** `{mb:.2f} MB`"
                )
                self.last_update = now
            except: pass

async def get_zip_filenames(client, message):
    """Threaded peeker to explore every folder path in the ZIP."""
    filenames = []
    data_queue = queue.Queue(maxsize=1) 
    
    def sync_source():
        while True:
            chunk = data_queue.get()
            if chunk is None: break
            yield chunk

    def unzip_thread():
        try:
            for name, size, chunks in stream_unzip(sync_source()):
                filenames.append(name.decode('utf-8'))
                for _ in chunks: pass # Drain
                if len(filenames) >= 100: break
        except Exception as e:
            print(f"DEBUG: Peek Thread Error: {e}")
        finally:
            while not data_queue.empty(): data_queue.get()

    t = threading.Thread(target=unzip_thread)
    t.start()

    try:
        async for chunk in client.iter_download(message.media):
            data_queue.put(chunk)
            if not t.is_alive(): break
    finally:
        data_queue.put(None)
        t.join()
    return filenames

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    """Threaded stream from Telegram to Bunny.net."""
    data_queue = queue.Queue(maxsize=1)
    progress = Progress(client, status_msg, target_file)
    result = {"guid": None, "error": None}

    def sync_source():
        while True:
            chunk = data_queue.get()
            if chunk is None: break
            yield chunk

    def unzip_thread():
        try:
            for name, size, chunks in stream_unzip(sync_source()):
                if name.decode('utf-8') == target_file:
                    url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{result['guid']}"
                    r = requests.put(url, data=chunks, headers={"AccessKey": b_cfg['STREAM_KEY']})
                    if r.status_code != 200:
                        result["error"] = f"Bunny Error: {r.status_code}"
                    return
                for _ in chunks: pass
        except Exception as e:
            result["error"] = str(e)
        finally:
            while not data_queue.empty(): data_queue.get()

    # Create Video Object
    async with aiohttp.ClientSession() as session:
        create_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        async with session.post(create_url, json={"title": target_file.split('/')[-1]}, 
                                headers={"AccessKey": b_cfg['STREAM_KEY'], "content-type": "application/json"}) as resp:
            if resp.status != 200: return None, f"Create Error: {resp.status}"
            result["guid"] = (await resp.json())['guid']

    # Start Worker Thread
    t = threading.Thread(target=unzip_thread)
    t.start()

    # Download from Telegram
    bytes_sent = 0
    try:
        async for chunk in client.iter_download(message.media):
            data_queue.put(chunk)
            bytes_sent += len(chunk)
            await progress.update(bytes_sent)
            if not t.is_alive(): break
    finally:
        data_queue.put(None)
        t.join()
        gc.collect()

    return result["guid"], result["error"]
