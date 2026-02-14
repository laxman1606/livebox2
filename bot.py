import os
import asyncio
import logging
import base64
import urllib.parse
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from pyrogram.file_id import FileId, FileType
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation, InputFileLocation

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://tickwala.blogspot.com")
BOT_URL = os.environ.get("BOT_URL", "") # Koyeb Public Link
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("LiveboxFix", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="🚀 Livebox Bot is Active and Responding!")

# 🛠️ REDIRECTOR (Short Link Fix)
@routes.get("/v/{id}")
async def redirect_handler(request):
    try:
        short_id = request.match_info['id']
        decoded = base64.urlsafe_b64decode(short_id + '=' * (4 - len(short_id) % 4)).decode('utf-8')
        chat_id, msg_id = decoded.split(":")
        stream_link = f"{BOT_URL}/stream/{chat_id}/{msg_id}"
        long_url = f"{WEB_APP_URL}/?src={urllib.parse.quote(stream_link)}&name=Livebox_Video"
        return web.HTTPFound(location=long_url)
    except:
        return web.Response(status=404, text="Link Expired")

# 🚀 STREAMING ENGINE (Multi-Audio Support)
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

        # Direct Chunk Streaming (Raw)
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
    logger.info(f"Start command from {message.from_user.id}")
    await message.reply_text(f"👋 **Hello {message.from_user.first_name}!**\n\nI am Livebox Bot. Send me any video.")

@app.on_message(filters.private & (filters.video | filters.document))
async def media_handler(client, message):
    try:
        raw_data = f"{message.chat.id}:{message.id}"
        short_id = base64.urlsafe_b64encode(raw_data.encode('utf-8')).decode('utf-8').replace("=", "")
        
        final_url = f"{BOT_URL}/v/{short_id}"
        
        await message.reply_text(
            f"✅ **Link Generated!**\n\n🔗 `{final_url}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ PLAY IN LIVEBOX", url=final_url)]])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER ---
async def main():
    # 1. Start Web Server
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    
    # 2. Start Bot (With Webhook Deletion)
    await app.start()
    # Force delete webhook to ensure polling works
    await app.invoke(pyrogram.raw.functions.messages.SetTyping(peer=await app.resolve_peer("me"), action=pyrogram.raw.types.SendMessageTypingAction())) 
    # Cleaner way:
    await app.set_bot_commands([]) # Simple call to verify connection
    
    print("✅ Bot is LIVE on Koyeb!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    import pyrogram.raw
    asyncio.run(main())
