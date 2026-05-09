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

# --- UTILS & DISK OPTIMIZATION ---
def startup_cleanup():
    """Wipes the SSD of any leftover files and prepares temp folders."""
    targets = ['current_vault.zip', 'temp_out', 'extract_temp']
    for target in targets:
        try:
            if os.path.isfile(target): os.remove(target)
            elif os.path.isdir(target): shutil.rmtree(target)
        except: pass
    if not os.path.exists('temp_out'): os.makedirs('temp_out')
    print("🧹 Disk Optimization: Cleanup Complete.")

# --- AGGRESSIVE TREE LOGIC ---
def build_tree(paths):
    tree = {}
    for path in paths:
        if "__MACOSX" in path or ".DS_Store" in path:
            continue
        parts = path.split('/')
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
    return tree

def get_tree_lines(tree, prefix="", number_prefix=""):
    lines = []
    items = sorted(tree.items(), key=lambda x: (len(x[1]) == 0, x[0].lower()))
    for i, (name, subtree) in enumerate(items, 1):
        num = f"{number_prefix}{i}"
        if not subtree:
            lines.append(f"{prefix}{num}. `{name}`")
        else:
            lines.append(f"{prefix}{num}. 📂 **{name}**")
            lines.extend(get_tree_lines(subtree, prefix + "    ", num + "."))
    return lines

def get_path_map(tree, number_prefix="", current_path=""):
    mapping = {}
    items = sorted(tree.items(), key=lambda x: (len(x[1]) == 0, x[0].lower()))
    for i, (name, subtree) in enumerate(items, 1):
        num = f"{number_prefix}{i}"
        new_path = f"{current_path}/{name}" if current_path else name
        if not subtree:
            mapping[num] = new_path
        else:
            mapping.update(get_path_map(subtree, num + ".", new_path))
    return mapping

# --- PROGRESS CALLBACK ---
async def progress_callback(current, total, status_msg, start_time):
    now = time.time()
    if not hasattr(progress_callback, "last_update"):
        progress_callback.last_update = 0
    
    if now - progress_callback.last_update < 5: return
    progress_callback.last_update = now

    percent = (current / total) * 100
    cur_mb, tot_mb = current/(1024*1024), total/(1024*1024)
    elapsed = now - start_time
    speed = cur_mb / elapsed if elapsed > 0 else 0
    
    try:
        await status_msg.edit(
            f"📥 **Downloading Vault...**\n"
            f"📊 **Progress:** `{percent:.1f}%`\n"
            f"📁 **Data:** `{cur_mb:.1f} / {tot_mb:.1f} MB`\n"
            f"⚡ **Speed:** `{speed:.2f} MB/s`"
        )
    except: pass

# --- HANDLER ---
@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handler(event):
    # 1. PROCESS ZIP FILES
    if event.message.file and event.message.file.ext == ".zip":
        status = await event.reply("📥 **Initializing High-Speed Download...**")
        start_time = time.time()
        
        try:
            # Native download with cryptg acceleration (if in requirements.txt)
            local_zip = await client.download_media(
                event.message,
                "current_vault.zip",
                progress_callback=lambda c, t: progress_callback(c, t, status, start_time)
            )
            
            await status.edit("📂 **Download Complete. Scanning Archive...**")
            
            with zipfile.ZipFile(local_zip, 'r') as z:
                all_paths = [p for p in z.namelist() if not p.endswith('/') and "__MACOSX" not in p]
                
                tree = build_tree(all_paths)
                all_lines = get_tree_lines(tree)
                path_map = get_path_map(tree)
                active_sessions[event.chat_id] = {"zip": local_zip, "map": path_map}
                
                await status.delete()
                await event.respond(f"✅ **Scan Complete!**\n📦 Total Items: `{len(all_paths)}`\n━━━━━━━━━━━━━━━━━━━━")
                
                # Chunked messaging to avoid Telegram character limits
                for i in range(0, len(all_lines), 25):
                    await event.respond("\n".join(all_lines[i : i + 25]))
                
                await event.respond("🔢 **Type indices to vault (e.g., 1.1 2.4.1)**")

        except Exception:
            await event.respond(f"❌ **Error:**\n`{traceback.format_exc()[-500:]}`")
            startup_cleanup()

    # 2. PROCESS VAULT COMMANDS
    elif event.text and event.chat_id in active_sessions:
        session = active_sessions[event.chat_id]
        targets = event.text.split()
        
        for num in targets:
            clean_num = num.strip('.')
            if clean_num in session['map']:
                real_path = session['map'][clean_num]
                status = await event.reply(f"🚀 **Vaulting:** `{real_path.split('/')[-1]}`")
                
                try:
                    with zipfile.ZipFile(session['zip'], 'r') as z:
                        ext_path = z.extract(real_path, "temp_out")
                    
                    guid, err = await upload_local_file_to_bunny(ext_path, real_path, BUNNY_CFG)
                    
                    if guid:
                        await status.edit(f"✅ **Vaulted {clean_num}:**\n🔗 `https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{guid}`")
                    else:
                        await status.edit(f"❌ **Failed:** {err}")
                    
                    if os.path.exists(ext_path): os.remove(ext_path)
                except Exception as e:
                    await status.edit(f"❌ **Crash:** `{e}`")

async def start():
    startup_cleanup()
    await client.start()
    print("🚀 Vault Service Online - No Files Will Be Skipped.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(start())
