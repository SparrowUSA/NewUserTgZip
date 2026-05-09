import os
import requests
import aiohttp

async def upload_local_file_to_bunny(local_path, internal_path, b_cfg):
    """
    Directly uploads a file from the GitHub SSD to Bunny.net.
    
    Args:
        local_path (str): The actual path on disk where the file was extracted.
        internal_path (str): The path inside the ZIP (used to set the video title).
        b_cfg (dict): Dictionary containing STREAM_KEY and LIBRARY_ID.
    """
    # Extract just the filename for the title (e.g., 'Physics/Ch1/Lecture.mp4' -> 'Lecture.mp4')
    display_name = internal_path.split('/')[-1]
    
    # --- STEP 1: Create the Video Object in Bunny.net ---
    async with aiohttp.ClientSession() as session:
        url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos"
        headers = {
            "AccessKey": b_cfg['STREAM_KEY'],
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        
        try:
            async with session.post(url, json={"title": display_name}, headers=headers) as resp:
                if resp.status != 200:
                    return None, f"Create API Error: {resp.status}"
                
                data = await resp.json()
                guid = data.get('guid')
        except Exception as e:
            return None, f"Connection Error (Create): {str(e)}"

    # --- STEP 2: Upload the actual File Content ---
    try:
        put_url = f"https://video.bunnycdn.com/library/{b_cfg['LIBRARY_ID']}/videos/{guid}"
        
        # We use a standard with open() block to stream the file from disk
        with open(local_path, 'rb') as f:
            # Using requests here is more stable for large local binary uploads
            r = requests.put(
                put_url, 
                data=f, 
                headers={"AccessKey": b_cfg['STREAM_KEY']}
            )
            
            if r.status_code == 200:
                return guid, None
            else:
                return None, f"Upload API Error: {r.status_code}"
                
    except Exception as e:
        return None, f"Connection Error (Upload): {str(e)}"
