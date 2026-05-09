import os
import asyncio
import zipfile
import traceback
from telethon import TelegramClient, events
from telethon.sessions import StringSession 
from dotenv import load_dotenv
from utils import upload_local_file_to_bunny

load_dotenv()

client = TelegramClient(StringSession(os.getenv("SESSION")), int(os.getenv("API_ID")), os.getenv("API_HASH"))
BUNNY_CFG = {
    "STREAM_KEY": os.getenv("BUNNY_STREAM_API_KEY"),
    "LIBRARY_ID": os.getenv("BUNNY_LIBRARY_ID"),
}

# Stores { chat_id: { "zip": path, "map": { "1.1": "folder/file.ts" } } }
active_sessions = {}

def build_tree(paths):
    """Converts flat paths into a nested numbered dictionary."""
    tree = {}
    for path in paths:
        parts = path.split('/')
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
    return tree

def format_tree(tree, prefix="", number_prefix=""):
    """Recursively builds the text list with numbers like 1.1.2"""
    lines = []
    for i, (name, subtree) in enumerate(tree.items(), 1):
        current_number = f"{number_prefix}{i}"
        if not subtree:  # It's a file
            lines.append(f"{prefix}{current_number}. `{name}`")
        else:  # It's a folder
            lines.append(f"{prefix}{current_number}. 📂 **{name}**")
            lines.extend(format_tree(subtree, prefix + "    ", current_number + "."))
    return lines

def get_path_map(tree, number_prefix="", current_path=""):
    """Maps the '1.1.2' string back to the actual 'folder/file.ts' path."""
    mapping = {}
    for i, (name, subtree) in enumerate(tree.items(), 1):
        num = f"{number_prefix}{i}"
        new_path = f"{current_path}/{name}" if current_path else name
        if not subtree:
            mapping[num] = new_path
        else:
            mapping.update(get_path_map(subtree, num + ".", new_path))
    return mapping

@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handler(event):
    # 1. SCAN ZIP
    if event.message.file and event.message.file.ext == ".zip":
        status = await event.reply("📥 **GitHub Action: Downloading large ZIP...**")
        local_zip = await event.download_media("current_vault.zip")
        
        with zipfile.ZipFile(local_zip, 'r') as z:
            # Clean list (remove hidden files like __MACOSX)
            paths = [f for f in z.namelist() if not f.startswith('__') and not f.endswith('/')]
            
            tree = build_tree(paths)
            tree_text = format_tree(tree)
            path_map = get_path_map(tree)
            
            active_sessions[event.chat_id] = {"zip": local_zip, "map": path_map}
            
            header = "🌳 **File Tree Structure:**\n━━━━━━━━━━━━━━━━━━━━\n"
            body = "\n".join(tree_text)
            footer = "\n\n🔢 **Type the number(s) to upload (e.g., 1.1 or 2.1.3)**"
            
            full_msg = header + body + footer
            for x in range(0, len(full_msg), 4000):
                await event.respond(full_msg[x:x+4000])
        await status.delete()

    # 2. PROCESS NUMBER INPUT
    elif event.text and event.chat_id in active_sessions:
        session = active_sessions[event.chat_id]
        targets = event.text.split() # Supports multiple: "1.1 2.2"
        
        for num in targets:
            clean_num = num.strip('.')
            if clean_num in session['map']:
                real_path = session['map'][clean_num]
                status = await event.reply(f"🚀 **Vaulting:** `{real_path}`")
                
                with zipfile.ZipFile(session['zip'], 'r') as z:
                    ext_path = z.extract(real_path, "temp_out")
                
                guid, err = await upload_local_file_to_bunny(ext_path, real_path, BUNNY_CFG)
                if guid:
                    await status.edit(f"✅ **Vaulted {clean_num}:**\n`https://iframe.mediadelivery.net/play/{BUNNY_CFG['LIBRARY_ID']}/{guid}`")
                else:
                    await status.edit(f"❌ Error on {clean_num}: {err}")
                
                if os.path.exists(ext_path): os.remove(ext_path)

async def main():
    await client.start()
    print("✅ Tree-Bot Active on GitHub...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
