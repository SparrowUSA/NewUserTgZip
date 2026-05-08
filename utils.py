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
    """
    THREADED PEEKER:
    Lists all files in a ZIP instantly by reading only the first 10MB.
    """
    filenames = []
    data_queue = queue.Queue(maxsize=10) 
    
    def sync_source():
        while True:
            try:
                # 20s timeout ensures we never hang if the stream breaks
                chunk = data_queue.get(timeout=20)
                if chunk is None: break
                yield chunk
            except queue.Empty:
                break

    def unzip_thread():
        try:
            for name, size, chunks in stream_unzip(sync_source()):
                fname = name.decode('utf-8')
                filenames.append(fname)
                # Drain chunks to find the next file header
                for _ in chunks: pass
                # Stop if we hit 100 files to keep the list manageable
                if len(filenames) >= 100: break
        except Exception as e:
            print(f"DEBUG: Peek Thread Error: {e}")
        finally:
            # Prevent blocking the main loop
            while not data_queue.empty():
                try: data_queue.get_nowait()
                except: break

    t = threading.Thread(target=unzip_thread, daemon=True)
    t.start()

    try:
        bytes_peeked = 0
        async for chunk in client.iter_download(message.media):
            if not t.is_alive(): break
            data_queue.put(chunk)
            bytes_peeked += len(chunk)
            # PEAK CAP: Only download first 10MB to get file list
            if bytes_peeked > 10 * 1024 * 1024: break 
    finally:
        data_queue.put(None)
        t.join(timeout=2)
    
    return filenames

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    """
    THREADED UPLOADER:
    Streams data from Telegram -> Queue -> stream_unzip -> Bunny.net.
    """
    data_queue = queue.Queue(maxsize=5)
    progress = Progress(client, status_msg, target_file)
    result = {"guid": None, "error": None}

    def sync_source():
        while True:
            try:
                chunk = data_queue.get(timeout=60) # 1 minute timeout for slow downloads
                if chunk is None: break
                yield chunk
            except queue.Empty:
                break

    def unzip_thread():
        try:
            for name, size, chunks in stream_unzip(sync_source()):
                if name.decode('utf-8') == target_file:
                    url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{result['guid']}"
                    r = requests.put(url, data=chunks, headers={"AccessKey": b_cfg['STREAM_KEY']}, timeout=None)
                    if r.status_code != 200:
                        result["error"] = f"Bunny Error: {r.status_code}"
                    return
                for _ in chunks: pass
        except Exception as e:
            result["error"] = str(e)
        finally:
            while not data_queue.empty():
                try: data_queue.get_nowait()
                except: break

    # 1. Create Video Object in Bunny
    async with aiohttp.ClientSession() as session:
        create_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        async with session.post(create_url, json={"title": target_file.split('/')[-1]}, 
                                headers={"AccessKey": b_cfg['STREAM_KEY'], "content-type": "application/json"}) as resp:
            if resp.status != 200: return None, f"Create Error: {resp.status}"
            result["guid"] = (await resp.json())['guid']

    # 2. Start the processing thread
    t = threading.Thread(target=unzip_thread, daemon=True)
    t.start()

    # 3. Feed the thread with data from Telegram
    bytes_sent = 0
    try:
        async for chunk in client.iter_download(message.media):
            data_queue.put(chunk)
            bytes_sent += len(chunk)
            await progress.update(bytes_sent)
            if not t.is_alive(): break
    finally:
        data_queue.put(None)
        t.join(timeout=10)
        gc.collect()

    return result["guid"], result["error"]
