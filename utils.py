import os
import requests
import aiohttp

async def upload_local_file_to_bunny(local_path, internal_path, b_cfg):
    """Directly uploads a file from the GitHub SSD to Bunny.net"""
    file_name = internal_path.split('/')[-1]
    
    # Create the Video Object
    async with aiohttp.ClientSession() as session:
        url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        headers = {"AccessKey": b_cfg['STREAM_KEY'], "Content-Type": "application/json"}
        async with session.post(url, json={"title": file_name}, headers=headers) as resp:
            if resp.status != 200: return None, "Bunny API Create Error"
            guid = (await resp.json())['guid']

    # Upload the actual binary data
    try:
        put_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{guid}"
        with open(local_path, 'rb') as f:
            # We use requests here for stable local file streaming
            r = requests.put(put_url, data=f, headers={"AccessKey": b_cfg['STREAM_KEY']})
            if r.status_code == 200:
                return guid, None
            return None, f"Upload Failed: {r.status_code}"
    except Exception as e:
        return None, str(e)
