import gc
import aiohttp
import traceback
import time
from stream_unzip import stream_unzip

class Progress:
    """
    Handles 10-second status updates to prevent Telegram spam filters
    while keeping you informed of the transfer progress.
    """
    def __init__(self, client, status_msg, file_name):
        self.client = client
        self.status_msg = status_msg
        self.file_name = file_name
        self.last_update = 0

    async def update(self, current_bytes):
        now = time.time()
        # Only update the message every 10 seconds
        if now - self.last_update > 10:
            mb = current_bytes / (1024 * 1024)
            try:
                await self.client.edit_message(
                    self.status_msg.chat_id,
                    self.status_msg.id,
                    f"🛠 **Streaming:** `{self.file_name}`\n📤 **Transferred:** `{mb:.2f} MB`\n🕒 **Status:** Active"
                )
                self.last_update = now
            except Exception as e:
                print(f"DEBUG: Progress update skipped: {e}")

async def stream_to_bunny_vault(client, message, target_file, b_cfg, status_msg):
    """
    Zero-Disk Pipe: Telegram -> Render RAM -> Bunny Stream API.
    Includes error reporting and memory cleanup.
    """
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
            # STEP 1: Create Video Object in Bunny Stream
            create_url = f"https://video.bunnycdn.com/library/{lib_id}/videos"
            async with session.post(create_url, json={"title": target_file}, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return None, f"Bunny Create Error ({resp.status}): {error_text}"
                
                video_data = await resp.json()
                video_guid = video_data['guid']

            # STEP 2: Logic to stream from Telegram
            async def telegram_generator():
                bytes_sent = 0
                async for chunk in client.iter_download(message.media):
                    yield chunk
                    bytes_sent += len(chunk)
                    await progress.update(bytes_sent)

            # STEP 3: Peek and Pipe
            found = False
            try:
                # Iterate through ZIP members without extracting to disk
                for name, size, unzipped_chunks in stream_unzip(telegram_generator()):
                    current_name = name.decode('utf-8')
                    
                    if current_name == target_file:
                        found = True
                        upload_url = f"https://video.bunnycdn.com/library/{lib_id}/videos/{video_guid}"
                        upload_headers = {"AccessKey": api_key, "accept": "application/json"}
                        
                        # Direct PUT request using the unzipped chunk generator
                        async with session.put(upload_url, data=unzipped_chunks, headers=upload_headers) as up_resp:
                            gc.collect() # Immediate memory purge
                            if up_resp.status == 200:
                                return video_guid, None
                            else:
                                up_err = await up_resp.text()
                                return None, f"Bunny Upload Error ({up_resp.status}): {up_err}"
                    else:
                        # Drain chunks of files we aren't looking for to keep the stream moving
                        for _ in unzipped_chunks:
                            pass
                            
            except Exception as e:
                return None, f"Streaming/Unzip Error: {str(e)}"

            if not found:
                return None, f"File `{target_file}` was not found inside the ZIP archive."

    except Exception:
        # Returns the full traceback to Telegram so you can debug instantly
        return None, f"Critical System Crash:\n```{traceback.format_exc()}```"

    return None, "Unexpected stream termination."
