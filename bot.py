import os
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from pyrogram.file_id import FileId, FileType
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation, InputFileLocation

# --- ⚙️ CONFIGURATION (Koyeb Settings se lega) ---
API_ID = int(os.environ.get("API_ID", 30763699))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# 1. Koyeb URL (Deploy hone ke baad jo link milega wo yaha bot automatic detect karega)
BOT_URL = os.environ.get("BOT_URL", "") 

# 2. Apka WebApp Link (Blogger/Netlify)
WEB_APP_URL = os.environ.get("WEB_APP_URL", "")

PORT = int(os.environ.get("PORT", 8000))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
app = Client("KoyebBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# --- 🛠️ BYTE STREAMER (Low RAM Logic) ---
class ByteStreamer:
    def __init__(self, client: Client, file_id: FileId):
        self.client = client
        if file_id.file_type in (FileType.VIDEO, FileType.DOCUMENT, FileType.AUDIO):
            self.location = InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=""
            )
        else:
            self.location = InputFileLocation(
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                secret=file_id.secret,
                file_reference=file_id.file_reference
            )

    async def yield_chunk(self, offset, chunk_size, limit):
        while limit > 0:
            to_read = min(limit, chunk_size)
            try:
                result = await self.client.invoke(GetFile(location=self.location, offset=offset, limit=to_read))
                yield result.bytes
                offset += len(result.bytes)
                limit -= len(result.bytes)
                if len(result.bytes) < to_read: break 
            except: break

# --- 🌐 WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="🚀 Koyeb Streamer is Live!")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        message = await app.get_messages(chat_id, message_id)
        media = message.video or message.document or message.audio
        
        if not media: return web.Response(status=404)

        file_id_obj = FileId.decode(media.file_id)
        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "video/mp4")

        range_header = request.headers.get("Range", 0)
        from_bytes, until_bytes = 0, file_size - 1
        if range_header:
            try:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else file_size - 1
            except: pass
        
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(until_bytes - from_bytes + 1),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        }

        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        streamer = ByteStreamer(app, file_id_obj)
        async for chunk in streamer.yield_chunk(from_bytes, 1024*1024, until_bytes - from_bytes + 1):
            try: await response.write(chunk)
            except: break
        return response
    except: return web.Response(status=500)

# --- 📩 BOT HANDLERS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **Koyeb Streamer Ready!**\nSend me any video to get the player link.")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_media(client, message):
    try:
        # Check if BOT_URL is set
        if not BOT_URL:
            return await message.reply_text("❌ Error: BOT_URL is not set in Koyeb Settings!")

        raw_data = f"{message.chat.id}:{message.id}"
        short_id = urllib.parse.quote(raw_data) # Simple Encoding
        
        # Stream Link Generator
        stream_link = f"{BOT_URL}/stream/{message.chat.id}/{message.id}"
        fname = urllib.parse.quote(getattr(message.video or message.document, "file_name", "Video"))
        
        # Web App Final Link
        final_url = f"{WEB_APP_URL}/?src={stream_link}&name={fname}"
        
        await message.reply_text(
            f"✅ **Link Ready!**\n\n👇 Click below to watch online:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch Online", url=final_url)]])
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
    print("✅ Bot Started on Koyeb!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())