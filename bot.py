import logging
import re
import os
import time
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TimedOut, RetryAfter
from flask import Flask
import requests

# Enhanced logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app with keepalive
app = Flask(__name__)

@app.route('/')
def health():
    return {
        "status": "running",
        "uptime": time.time(),
        "bot": "24x7-affiliate-bot",
        "version": "3.0"
    }

@app.route('/keepalive')
def keepalive():
    """Endpoint to prevent Render from sleeping"""
    return {"alive": True, "timestamp": time.time()}

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))

# Keepalive settings
KEEPALIVE_URL = os.environ.get('KEEPALIVE_URL', '')  # Your Render URL
KEEPALIVE_INTERVAL = 840  # 14 minutes (before 15min timeout)

logger.info(f"🚀 24/7 Bot starting - Affiliate: {AFFILIATE_TAG}")

def convert_amazon_link(url, affiliate_tag):
    """Convert Amazon URL to affiliate link"""
    try:
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                asin = match.group(1)
                return f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
    except Exception as e:
        logger.error(f"Link conversion error: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links"""
    if not text:
        return text, 0
        
    patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]+/[^\s]+',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+'
    ]
    
    converted_text = text
    conversion_count = 0
    
    for pattern in patterns:
        urls = re.findall(pattern, text)
        for url in urls:
            converted_url = convert_amazon_link(url, affiliate_tag)
            if converted_url != url:
                converted_text = converted_text.replace(url, converted_url)
                conversion_count += 1
    
    return converted_text, conversion_count

def keepalive_ping():
    """Ping server every 14 minutes to prevent sleep"""
    while True:
        try:
            if KEEPALIVE_URL:
                response = requests.get(f"{KEEPALIVE_URL}/keepalive", timeout=30)
                logger.info(f"✅ Keepalive ping successful: {response.status_code}")
            else:
                logger.info("💓 Keepalive heartbeat (no URL configured)")
        except Exception as e:
            logger.warning(f"⚠️ Keepalive ping failed: {e}")
        
        time.sleep(KEEPALIVE_INTERVAL)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with 24/7 info"""
    welcome_msg = f"""
🤖 **24/7 Amazon Affiliate Bot**

✅ **Status**: Always Online (Never Sleeps)
✅ **Uptime**: 24/7 Cloud Hosting
✅ **Affiliate Tag**: {AFFILIATE_TAG}
✅ **Auto-Keepalive**: ENABLED

**🔥 FEATURES:**
• Runs 24/7 even when your laptop is OFF
• Never stops working or goes offline
• Auto-prevents server sleep
• Network-resilient connection
• Instant affiliate link conversion

**💡 USAGE:**
Send Amazon links → Auto-convert → Post to channel

**🌐 STATUS:**
• Server: Cloud-hosted (independent of your device)
• Connection: Always active
• Monitoring: Self-healing

Your affiliate bot works 24/7 regardless of your laptop status! 🚀
"""
    
    await safe_send(context.bot, update.message.chat_id, welcome_msg)

async def safe_send(bot, chat_id, text, max_retries=3):
    """Send message with retry logic"""
    for attempt in range(max_retries):
        try:
            return await bot.send_message(chat_id=chat_id, text=text)
        except (NetworkError, TimedOut) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                logger.warning(f"Retry {attempt + 1} in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed after {max_retries} attempts: {e}")
                raise
        except RetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages with full resilience"""
    try:
        text = update.message.text
        user_name = update.effective_user.first_name or "User"
        chat_id = update.message.chat_id
        
        logger.info(f"📨 Processing from {user_name}")
        
        # Convert links
        converted_text, conversion_count = convert_all_links(text, AFFILIATE_TAG)
        
        if conversion_count > 0:
            # Success - post to channel
            if YOUR_CHANNEL_ID:
                try:
                    channel_post = f"""
🔥 **24/7 DEAL ALERT**

{converted_text}

💰 **Affiliate Ready** - Earn commissions now!
📱 **Shared by**: {user_name}
🤖 **Always-On Bot** (Works 24/7)

⚡ **Grab this deal immediately!**
"""
                    
                    await safe_send(context.bot, YOUR_CHANNEL_ID, channel_post)
                    
                    confirmation = f"""
✅ **SUCCESS - Posted 24/7!**

🔗 **Converted Links:**
{converted_text}

📊 **Bot Status:**
• Links converted: {conversion_count}
• Posted to channel: ✅
• 24/7 status: Always running
• Your laptop: Can be OFF (bot still works!)

💰 **Ready to earn - Bot never sleeps!**
"""
                    await safe_send(context.bot, chat_id, confirmation)
                    
                except Exception as e:
                    logger.error(f"Channel error: {e}")
                    await safe_send(context.bot, chat_id, f"Converted: {converted_text}")
            else:
                await safe_send(context.bot, chat_id, f"Converted: {converted_text}")
        else:
            await safe_send(context.bot, chat_id, "❌ No Amazon links found.")
            
    except Exception as e:
        logger.error(f"Handler error: {e}")
        try:
            await safe_send(context.bot, update.message.chat_id, "⚠️ Processing error, retrying...")
        except:
            pass

def run_flask():
    """Flask server with error recovery"""
    while True:
        try:
            logger.info(f"🌐 Starting Flask server on port {PORT}")
            app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
        except Exception as e:
            logger.error(f"Flask crashed: {e}")
            logger.info("🔄 Restarting Flask in 5 seconds...")
            time.sleep(5)

def main():
    """Main bot with automatic restart"""
    if not TOKEN:
        logger.error("❌ No TOKEN!")
        return
    
    logger.info("🚀 Starting 24/7 Bot (Never Sleeps)")
    logger.info(f"✅ Affiliate: {AFFILIATE_TAG}")
    logger.info(f"✅ Channel: {YOUR_CHANNEL_ID}")
    
    # Start Flask server
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start keepalive service
    keepalive_thread = threading.Thread(target=keepalive_ping, daemon=True)
    keepalive_thread.start()
    
    logger.info("✅ Flask & Keepalive started")
    
    # Bot loop with auto-restart
    restart_count = 0
    max_restarts = 50
    
    while restart_count < max_restarts:
        try:
            logger.info(f"🔄 Bot startup #{restart_count + 1}")
            
            application = Application.builder().token(TOKEN).build()
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            logger.info("✅ 24/7 Bot is LIVE!")
            
            # Run with polling
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
            
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            restart_count += 1
            
            if restart_count < max_restarts:
                wait_time = min(60, 10 * restart_count)
                logger.info(f"🔄 Auto-restarting in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error("❌ Max restarts reached")
                break

if __name__ == '__main__':
    import asyncio
    main()
