import os
import asyncio
import logging
import base64
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from pyrogram.file_id import FileId
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://tickwala.blogspot.com")
BOT_URL = os.environ.get("BOT_URL", "") # Koyeb App Link
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("LiveboxFix", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="✅ Bot is Online!")

# 🚀 STREAMING ENGINE
@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        message = await app.get_messages(chat_id, message_id)
        media = message.video or message.document or message.audio
        
        file_id_obj = FileId.decode(media.file_id)
        file_size = media.file_size
        
        range_header = request.headers.get("Range", 0)
        from_bytes, until_bytes = 0, file_size - 1
        if range_header:
            try:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else file_size - 1
            except: pass
        
        headers = {
            "Content-Type": getattr(media, "mime_type", "video/mp4"),
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(until_bytes - from_bytes + 1),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        }

        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        location = InputDocumentFileLocation(id=file_id_obj.media_id, access_hash=file_id_obj.access_hash, file_reference=file_id_obj.file_reference, thumb_size="")
        
        offset = from_bytes
        limit = until_bytes - from_bytes + 1
        while limit > 0:
            chunk = await app.invoke(GetFile(location=location, offset=offset, limit=min(limit, 1024*1024)))
            if not chunk.bytes: break
            await response.write(chunk.bytes)
            offset += len(chunk.bytes)
            limit -= len(chunk.bytes)
        return response
    except: return web.Response(status=500)

# --- BOT HANDLERS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(f"👋 **Hi {message.from_user.first_name}!** Send video.")

@app.on_message(filters.private & (filters.video | filters.document))
async def media_handler(client, message):
    try:
        raw_data = f"{message.chat.id}:{message.id}"
        short_id = base64.urlsafe_b64encode(raw_data.encode()).decode().replace("=", "")
        final_url = f"{WEB_APP_URL}/?src={BOT_URL}/stream/{message.chat.id}/{message.id}&name=Video"
        
        await message.reply_text(
            f"✅ **Link Ready!**\n\n🔗 `{final_url}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ PLAY", url=final_url)]])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER ---
async def main():
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await app.start()
    print("✅ Bot Started!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
