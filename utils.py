import gc
import aiohttp
from stream_unzip import stream_unzip

async def stream_to_bunny(client, message, target_file, b_cfg):
    """
    Pipes bytes: Telegram -> Render RAM -> Bunny.net
    Cleans memory after every chunk to prevent OOM on Render.
    """
    async def telegram_generator():
        async for chunk in client.iter_download(message.media):
            yield chunk

    async with aiohttp.ClientSession() as session:
        # name is bytes, target_file is string
        for name, size, unzipped_chunks in stream_unzip(telegram_generator()):
            current_name = name.decode('utf-8')
            
            if current_name == target_file:
                storage_url = f"https://storage.bunnycdn.com/{b_cfg['ZONE']}/{target_file}"
                headers = {
                    "AccessKey": b_cfg['KEY'],
                    "Content-Type": "application/octet-stream"
                }
                
                async with session.put(storage_url, data=unzipped_chunks, headers=headers) as resp:
                    # Trigger garbage collection immediately after stream
                    del unzipped_chunks
                    gc.collect()
                    return resp.status in [200, 201]
            else:
                # Consume and discard chunks of files we don't want
                for _ in unzipped_chunks:
                    pass
    return False
