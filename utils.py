import os
import requests
import aiohttp

async def upload_local_file_to_bunny(local_path, internal_path, b_cfg):
    display_name = internal_path.split('/')[-1]
    
    # 1. Create Video Entry
    async with aiohttp.ClientSession() as session:
        url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        headers = {
            "AccessKey": b_cfg['STREAM_KEY'],
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        async with session.post(url, json={"title": display_name}, headers=headers) as resp:
            if resp.status != 200:
                return None, f"Create Error: {resp.status}"
            data = await resp.json()
            guid = data.get('guid')

    # 2. Stream Upload (Disk to Web)
    try:
        put_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{guid}"
        with open(local_path, 'rb') as f:
            r = requests.put(put_url, data=f, headers={"AccessKey": b_cfg['STREAM_KEY']})
            if r.status_code == 200:
                return guid, None
            return None, f"Upload Error: {r.status_code}"
    except Exception as e:
        return None, str(e)
