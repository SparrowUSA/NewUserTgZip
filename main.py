import os
import shutil
import zipfile
import traceback
import time
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession 
from dotenv import load_dotenv
from utils import upload_local_file_to_bunny

load_dotenv()

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
active_sessions = {}

# --- UTILS & CLEANUP ---
def startup_cleanup():
    """Wipes the SSD of any leftover files from previous runs."""
    targets = ['current_vault.zip', 'temp_out', 'extract_temp', 'out']
    for target in targets:
        try:
            if os.path.isfile(target): os.remove(target)
            elif os.path.isdir(target): shutil.rmtree(target)
        except: pass
    if not os.path.exists('temp_out'): os.makedirs('temp_out')
    print("🧹 Disk Cleanup Complete.")

# --- TREE LOGIC ---
def build_tree(paths):
    tree = {}
    for path in paths:
        parts = path.split('/')
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
    return tree

def get_tree_lines(tree, prefix="", number_prefix=""):
    """Generates the visual list lines recursively."""
    lines = []
    items = sorted(tree.items())
    for i, (name, subtree) in enumerate(items, 1):
        num = f"{number_prefix}{i}"
        if not subtree: # It's a file
            lines.append(f"{prefix}{num}. `{name}`")
        else: # It's a folder
            lines.append(f"{prefix}{num}. 📂 **{name}**")
            lines.extend(get_tree_lines(subtree, prefix + "    ", num + "."))
    return lines

def get_path_map(tree, number_prefix="", current_path=""):
    """Maps '1.2.1' style strings to actual internal ZIP paths."""
    mapping = {}
    items = sorted(tree.items())
    for i, (name, subtree) in enumerate(items, 1):
        num = f"{number_prefix}{i}"
        new_path = f"{current_path}/{name}" if current_path else name
        if not subtree:
            mapping[num] = new_path
        else:
            mapping.update(get_path_map(subtree, num + ".", new_path))
    return mapping

# --- DOWNLOAD PROGRESS ---
async def progress_callback(current, total, status_msg, start_time):
    now = time.time()
    if not hasattr(progress_callback, "last_update"):
        progress_callback.last_update = 0
    
    if now - progress_callback.last_update < 5: return
    progress_callback.last_update = now

    percent = (current / total) * 100
    cur_mb, tot_mb = current/(1024*1024), total/(1024*1024)
    speed = cur_mb / (now - start_time) if (now - start_time) > 0 else 0
    
    try:
        await status_msg.edit(
            f"📥 **Downloading ZIP...**\n"
            f"📊 **Progress:** `{percent:.1f}%`\n"
            f"📁 **Size:** `{cur_mb:.1f} / {tot_mb:.1f} MB`\n"
            f"⚡ **Speed:** `{speed:.2f} MB/s`"
        )
    except: pass

# --- MAIN HANDLER ---
@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handler(event):
    # 1. HANDLE ZIP FORWARD
    if event.message.file and event.message.file.ext == ".zip":
        status = await event.reply("📥 **Initializing Secure Download...**")
        start_time = time.time()
        
        try:
            # Download to GitHub SSD
            local_zip = await event.download_media(
                "current_vault.zip",
                progress_callback=lambda c, t: progress_callback(c, t, status, start_time)
            )
            
            await status.edit("📂 **Download Complete. Generating Tree...**")
            
            with zipfile.ZipFile(local_zip, 'r') as z:
                # Filter out system files
                paths = [f for f in z.namelist() if not f.startswith('__') and not f.endswith('/')]
                
                tree = build_tree(paths)
                all_lines = get_tree_lines(tree)
                path_map = get_path_map(tree)
                active_sessions[event.chat_id] = {"zip": local_zip, "map": path_map}
                
                await status.delete()
                await event.respond(f"🌳 **File Tree ({len(paths)} items):**\n━━━━━━━━━━━━━━━━━━━━")
                
                # Chunked messaging to avoid skipping files
                chunk_size = 30
                for i in range(0, len(all_lines), chunk_size):
                    await event.respond("\n".join(all_lines[i : i + chunk_size]))
                
                await event.respond("🔢 **Type number(s) to upload (e.g. 1.2 3.1.4)**")

        except Exception:
            await event.respond(f"❌ **Error:**\n`{traceback.format_exc()[:500]}`")
            startup_cleanup()

    # 2. HANDLE NUMBER INPUT
    elif event.text and event.chat_id in active_sessions:
        session = active_sessions[event.chat_id]
        targets = event.text.split()
        
        for num in targets:
            clean_num = num.strip('.')
            if clean_num in session['map']:
                real_path = session['map'][clean_num]
                status = await event.reply(f"🚀 **Vaulting:** `{real_path.split('/')[-1]}`")
                
                try:
                    # Extract single file
                    with zipfile.ZipFile(session['zip'], 'r') as z:
                        ext_path = z.extract(real_path, "temp_out")
                    
                    # Upload to Bunny
                    guid, err = await upload_local_file_to_bunny(ext_path, real_path, BUNNY_CFG)
                    
                    if guid:
                        await status.edit(f"✅ **Vaulted {clean_num}:**\n🔗 `https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{guid}`")
                    else:
                        await status.edit(f"❌ **Upload Failed:** {err}")
                    
                    # Immediate Cleanup of extracted file
                    if os.path.exists(ext_path): os.remove(ext_path)
                
                except Exception as e:
                    await status.edit(f"❌ **Crash:** `{e}`")

async def start_bot():
    startup_cleanup()
    await client.start()
    print("🚀 Vault Tree Bot is online on GitHub Actions!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(start_bot())
