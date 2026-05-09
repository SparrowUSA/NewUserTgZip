import os
import requests
import aiohttp

async def upload_local_file_to_bunny(local_path, internal_path, b_cfg):
    """
    Uploads a file from GitHub SSD to Bunny.net Stream.
    Uses a 2-step process: Create Video -> Upload Content.
    """
    # Clean name for the Bunny.net dashboard (removes folder paths)
    display_name = internal_path.split('/')[-1]
    
    # --- STEP 1: CREATE VIDEO ENTRY ---
    # We use aiohttp for the quick metadata call
    async with aiohttp.ClientSession() as session:
        create_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        headers = {
            "AccessKey": b_cfg['STREAM_KEY'],
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        
        try:
            async with session.post(create_url, json={"title": display_name}, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return None, f"Entry Creation Failed ({resp.status}): {error_text}"
                
                data = await resp.json()
                guid = data.get('guid')
        except Exception as e:
            return None, f"Network Error during creation: {str(e)}"

    # --- STEP 2: STREAM BINARY CONTENT ---
    # We use requests for the heavy binary upload as it handles disk-streaming more reliably
    try:
        upload_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{guid}"
        upload_headers = {
            "AccessKey": b_cfg['STREAM_KEY'],
            "Content-Type": "application/octet-stream"
        }
        
        with open(local_path, 'rb') as f:
            # This streams the file from disk directly to the network
            r = requests.put(upload_url, data=f, headers=upload_headers)
            
            if r.status_code == 200:
                return guid, None
            else:
                return None, f"Upload Failed ({r.status_code}): {r.text}"
                
    except Exception as e:
        return None, f"Network Error during upload: {str(e)}"
