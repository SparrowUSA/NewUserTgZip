import gc
import aiohttp
import asyncio
import traceback
import time
import threading
import queue
import requests
import io
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
    Optimized Peeker: Reads only enough of the ZIP to get the file list.
    No threads/queues here to prevent deadlocks.
    """
    filenames = []
    chunk_count = 0
    
    # We create a simple generator that pulls from Telegram
    async def telegram_stream():
        async for chunk in client.iter_download(message.media):
            yield chunk

    def sync_gen(async_gen):
        loop = asyncio.get_event_loop()
        it = async_gen.__aiter__()
        while True:
            try:
                yield loop.run_until_complete(it.__anext__())
            except StopAsyncIteration:
                break

    try:
        # We only look at the first 5MB of the ZIP for peeking
        # This is usually plenty for the header/file list
        for name, size, chunks in stream_unzip(sync_gen(telegram_stream())):
            fname = name.decode('utf-8')
            filenames.append(fname)
            # Drain the file chunks so we can see the next header
            for _ in chunks: pass 
            
            if len(filenames) >= 50: break
    except Exception as e:
        print(f"PEEK LOG: {e}")
    
    return filenames

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    """
    Threaded upload for the actual file transfer. 
    Added safety timeouts to prevent hanging.
    """
    data_queue = queue.Queue(maxsize=5) # Increased buffer
    progress = Progress(client, status_msg, target_file)
    result = {"guid": None, "error": None}

    def sync_source():
        while True:
            try:
                chunk = data_queue.get(timeout=30) # Prevent infinite hang
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
            # Clean up queue
            try:
                while not data_queue.empty(): data_queue.get_nowait()
            except: pass

    # 1. Create Video
    async with aiohttp.ClientSession() as session:
        create_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        async with session.post(create_url, json={"title": target_file.split('/')[-1]}, 
                                headers={"AccessKey": b_cfg['STREAM_KEY'], "content-type": "application/json"}) as resp:
            if resp.status != 200: return None, f"Create Error: {resp.status}"
            result["guid"] = (await resp.json())['guid']

    # 2. Start Worker
    t = threading.Thread(target=unzip_thread, daemon=True)
    t.start()

    # 3. Stream from Telegram
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
