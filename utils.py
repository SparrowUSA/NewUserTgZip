import gc
import aiohttp
import traceback
import time
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
                    f"🛠 **Streaming:** `{self.file_name}`\n📤 **Transferred:** `{mb:.2f} MB`\n🕒 **Status:** Processing..."
                )
                self.last_update = now
            except: pass

async def get_zip_filenames(client, message):
    """Peeks at ZIP headers to list files without downloading the whole archive."""
    filenames = []
    async def telegram_generator():
        async for chunk in client.iter_download(message.media):
            yield chunk
    try:
        # We only iterate headers; stream_unzip is very efficient here
        for name, size, unzipped_chunks in stream_unzip(telegram_generator()):
            filenames.append(name.decode('utf-8'))
            for _ in unzipped_chunks: pass # Skip content
            if len(filenames) >= 15: break # Cap at 15 files for speed
    except Exception as e:
        print(f"DEBUG: Peek Error: {e}")
    return filenames

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    try:
        lib_id = b_cfg['LIBRARY_ID']
        api_key = b_cfg['STREAM_KEY']
        headers = {"AccessKey": api_key, "accept": "application/json", "content-type": "application/json"}
        progress = Progress(client, status_msg, target_file)
        
        async with aiohttp.ClientSession() as session:
            # Create Video Object
            create_url = f"https://video.bunnycdn.com/library/{lib_id}/videos"
            async with session.post(create_url, json={"title": target_file}, headers=headers) as resp:
                if resp.status != 200:
                    return None, f"Bunny API Error: {resp.status}"
                video_guid = (await resp.json())['guid']

            async def telegram_generator():
                bytes_sent = 0
                async for chunk in client.iter_download(message.media):
                    yield chunk
                    bytes_sent += len(chunk)
                    await progress.update(bytes_sent)

            found = False
            for name, size, unzipped_chunks in stream_unzip(telegram_generator()):
                if name.decode('utf-8') == target_file:
                    found = True
                    upload_url = f"https://video.bunnycdn.com/library/{lib_id}/videos/{video_guid}"
                    up_headers = {"AccessKey": api_key, "accept": "application/json"}
                    async with session.put(upload_url, data=unzipped_chunks, headers=up_headers) as up_resp:
                        gc.collect()
                        if up_resp.status == 200: return video_guid, None
                        return None, f"Upload Failed: {up_resp.status}"
                else:
                    for _ in unzipped_chunks: pass
            return None, "File not found in ZIP."
    except Exception:
        return None, f"Critical Error:\n```{traceback.format_exc()}```"
