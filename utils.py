import gc
import aiohttp
import asyncio
import traceback
import time
from stream_unzip import stream_unzip

class Progress:
    """Handles 10-second status updates to prevent Telegram rate-limiting."""
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
                    f"🛠 **Streaming:** `{self.file_name}`\n📤 **Transferred:** `{mb:.2f} MB`\n🕒 **Status:** Active"
                )
                self.last_update = now
            except: 
                pass

def to_sync_generator(async_gen, loop):
    """
    Bridge: Converts Telegram's Async Generator into a Sync Generator
    so stream_unzip can process it without __aiter__ errors.
    """
    def sync_gen():
        try:
            # We manually iterate the async generator using the existing loop
            it = async_gen.__aiter__()
            while True:
                try:
                    yield loop.run_until_complete(it.__anext__())
                except StopAsyncIteration:
                    break
        except Exception as e:
            print(f"DEBUG: Sync Wrapper Error: {e}")
    return sync_gen()

async def get_zip_filenames(client, message):
    """Peeks at ZIP headers to list files without downloading the archive."""
    filenames = []
    loop = asyncio.get_event_loop()
    
    async def telegram_generator():
        async for chunk in client.iter_download(message.media):
            yield chunk

    try:
        # Wrap the async telegram source into a sync-compatible generator
        sync_source = to_sync_generator(telegram_generator(), loop)
        
        # Now stream_unzip works with a standard 'for' loop
        for name, size, unzipped_chunks in stream_unzip(sync_source):
            filenames.append(name.decode('utf-8'))
            # Still need to drain the chunks to move to the next header
            for _ in unzipped_chunks:
                pass
            if len(filenames) >= 15: 
                break 
    except Exception as e:
        print(f"DEBUG: Peek Error: {e}")
        
    return filenames

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    """Direct pipe from Telegram to Bunny.net via Render RAM."""
    loop = asyncio.get_event_loop()
    try:
        lib_id = b_cfg['LIBRARY_ID']
        api_key = b_cfg['STREAM_KEY']
        headers = {
            "AccessKey": api_key, 
            "accept": "application/json", 
            "content-type": "application/json"
        }
        
        progress = Progress(client, status_msg, target_file)
        
        async with aiohttp.ClientSession() as session:
            # STEP 1: Create Video Object
            create_url = f"https://video.bunnycdn.com/library/{lib_id}/videos"
            async with session.post(create_url, json={"title": target_file}, headers=headers) as resp:
                if resp.status != 200:
                    return None, f"Bunny Create Error: {resp.status}"
                video_guid = (await resp.json())['guid']

            # STEP 2: Async Generator for Telegram
            async def telegram_generator():
                bytes_sent = 0
                async for chunk in client.iter_download(message.media):
                    yield chunk
                    bytes_sent += len(chunk)
                    await progress.update(bytes_sent)

            # STEP 3: Convert to Sync for stream_unzip and Pipe
            found = False
            sync_source = to_sync_generator(telegram_generator(), loop)
            
            for name, size, unzipped_chunks in stream_unzip(sync_source):
                if name.decode('utf-8') == target_file:
                    found = True
                    upload_url = f"https://video.bunnycdn.com/library/{lib_id}/videos/{video_guid}"
                    up_headers = {"AccessKey": api_key, "accept": "application/json"}
                    
                    # session.put accepts the unzipped_chunks generator directly
                    async with session.put(upload_url, data=unzipped_chunks, headers=up_headers) as up_resp:
                        gc.collect()
                        if up_resp.status == 200:
                            return video_guid, None
                        return None, f"Bunny Upload Error: {up_resp.status}"
                else:
                    for _ in unzipped_chunks: 
                        pass 
            
            if not found:
                return None, "File not found in ZIP."

    except Exception:
        return None, f"Critical Error:\n```{traceback.format_exc()}```"

    return None, "Unexpected error."
