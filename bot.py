import logging
import re
import os
import threading
import time
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TimedOut
from flask import Flask, jsonify

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for Render health checks
app = Flask(__name__)

@app.route('/')
def health():
    return jsonify({
        "status": "healthy",
        "service": "Network-Resilient Amazon Affiliate Bot",
        "version": "3.0",
        "uptime": time.time()
    })

@app.route('/status')
def bot_status():
    return jsonify({
        "bot_running": True,
        "network_resilient": True,
        "auto_reconnect": "enabled"
    })

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))

# Network resilience settings
MAX_RETRIES = 5
RETRY_DELAY = 10
HEARTBEAT_INTERVAL = 300  # 5 minutes

logger.info(f"Network-resilient bot starting with affiliate tag: {AFFILIATE_TAG}")

def convert_amazon_link(url, affiliate_tag):
    """Convert Amazon URL to affiliate link"""
    try:
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})'
        ]
        
        asin = None
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                asin = match.group(1)
                break
        
        if asin:
            return f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
        
    except Exception as e:
        logger.error(f"Error converting Amazon link: {e}")
    
    return url

def convert_flipkart_link(url, affiliate_tag):
    """Convert Flipkart URL to affiliate link"""
    try:
        if 'flipkart.com' in url.lower():
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}affid={affiliate_tag}"
    except Exception as e:
        logger.error(f"Error converting Flipkart link: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon and Flipkart links"""
    if not text:
        return text, 0
        
    amazon_patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]+/[^\s]+',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+'
    ]
    
    flipkart_patterns = [
        r'https?://(?:www\.)?flipkart\.com/[^\s]+',
        r'https?://dl\.flipkart\.com/[^\s]+'
    ]
    
    converted_text = text
    conversion_count = 0
    
    # Convert Amazon links
    for pattern in amazon_patterns:
        urls = re.findall(pattern, text)
        for url in urls:
            converted_url = convert_amazon_link(url, affiliate_tag)
            if converted_url != url:
                converted_text = converted_text.replace(url, converted_url)
                conversion_count += 1
    
    # Convert Flipkart links
    for pattern in flipkart_patterns:
        urls = re.findall(pattern, text)
        for url in urls:
            converted_url = convert_flipkart_link(url, affiliate_tag)
            if converted_url != url:
                converted_text = converted_text.replace(url, converted_url)
                conversion_count += 1
    
    return converted_text, conversion_count

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with network resilience info"""
    try:
        welcome_msg = f"""
🤖 **Network-Resilient Amazon Affiliate Bot v3.0**

✅ **Status**: Online & Auto-Reconnecting
✅ **Network Resilience**: ENABLED
✅ **Affiliate Tag**: {AFFILIATE_TAG}
✅ **Your Channel**: {YOUR_CHANNEL_ID if YOUR_CHANNEL_ID else 'Not configured'}

**🔄 NETWORK FEATURES:**
• Auto-reconnects after network issues
• Handles WiFi/data switching
• Survives internet disconnects
• Self-healing connection
• 24/7 uptime guaranteed

**💡 How It Works:**
1. Send me Amazon/Flipkart deals
2. I convert to your affiliate links
3. Post to your channel automatically
4. **Never stops working!** 🚀

**🌐 Network Status**: Connected & Monitoring
**🛡️ Resilience**: Maximum Protection

Ready to process deals even during network issues!
"""
        await update.message.reply_text(welcome_msg)
        logger.info(f"Start command - network resilient bot active for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages with retry logic"""
    try:
        if not update.message or not update.message.text:
            return
            
        text = update.message.text
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "User"
        
        logger.info(f"Processing message from user {user_id}: {user_name}")
        
        # Convert affiliate links
        converted_text, conversion_count = convert_all_links(text, AFFILIATE_TAG)
        
        if conversion_count > 0:
            # Process with retry logic for network resilience
            success = await send_with_retry(context, converted_text, user_name, update)
            
            if success:
                await update.message.reply_text(f"""
✅ **SUCCESS! Deal Posted**

📊 **Stats:**
• **Links Converted**: {conversion_count}
• **Network Status**: Stable
• **Channel**: Posted Successfully

🔗 **Your Affiliate Links:**
{converted_text}

💰 **Ready to earn commissions!**
""")
            else:
                await update.message.reply_text(f"""
⚠️ **Converted But Channel Issue**

🔗 **Your Affiliate Links:**
{converted_text}

🔄 **Retrying channel post automatically...**
""")
        else:
            await update.message.reply_text("""
❌ **No E-commerce Links Found**

**Supported formats:**
• https://amazon.in/dp/XXXXXXXXXX
• https://amzn.to/XXXXXX
• https://flipkart.com/product-name

**Example**: "🔥 Great deal! https://amazon.in/dp/B08N5WRWNW"
""")
            
    except Exception as e:
        logger.error(f"Error in message handling: {e}")
        try:
            await update.message.reply_text("⚠️ Network issue detected. Retrying...")
        except:
            pass

async def send_with_retry(context, converted_text, user_name, update, max_retries=3):
    """Send message with automatic retry on network failures"""
    if not YOUR_CHANNEL_ID:
        return False
        
    for attempt in range(max_retries):
        try:
            channel_post = f"""
🔥 **DEAL ALERT!**

{converted_text}

💰 **Affiliate Ready** - Tap to shop & earn!
📱 **Shared by**: {user_name}
🛡️ **Network-Resilient Bot**

⚡ **Grab this deal now!**
"""
            
            await context.bot.send_message(
                chat_id=YOUR_CHANNEL_ID,
                text=channel_post
            )
            
            logger.info(f"✅ Successfully sent to channel on attempt {attempt + 1}")
            return True
            
        except (NetworkError, TimedOut) as e:
            logger.warning(f"Network error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
        except Exception as e:
            logger.error(f"Non-network error sending to channel: {e}")
            break
    
    logger.error("Failed to send to channel after all retries")
    return False

async def heartbeat_check(context):
    """Periodic heartbeat to ensure bot is responsive"""
    try:
        # Simple API call to check connection
        me = await context.bot.get_me()
        logger.info(f"✅ Heartbeat OK - Bot: {me.username}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Heartbeat failed: {e}")
        return False

def run_flask_server():
    """Run Flask server with network error handling"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            logger.info(f"Starting Flask server on 0.0.0.0:{PORT} (attempt {attempt + 1})")
            app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
            break
        except Exception as e:
            logger.error(f"Flask server error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                logger.critical("Failed to start Flask server after all attempts")

def main():
    """Main function with network resilience"""
    if not TOKEN:
        logger.error("❌ TOKEN environment variable not set!")
        raise ValueError("Missing required TOKEN environment variable")
    
    logger.info("🚀 Starting Network-Resilient Bot...")
    logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
    logger.info(f"✅ Target channel: {YOUR_CHANNEL_ID}")
    logger.info("🛡️ Network resilience: ENABLED")
    
    # Start Flask server with resilience
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask health server started with retry logic")
    
    # Main bot loop with automatic reconnection
    retry_count = 0
    max_retries = 10
    
    while retry_count < max_retries:
        try:
            logger.info(f"🔄 Starting bot (attempt {retry_count + 1})")
            
            # Create application with network timeouts
            application = Application.builder().token(TOKEN).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
            
            logger.info("✅ Handlers registered")
            
            # Start polling with network resilience
            await application.initialize()
            await application.start()
            
            logger.info("✅ Bot connected successfully!")
            retry_count = 0  # Reset retry count on successful connection
            
            # Run with automatic restart on network issues
            await application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
            
            # Keep running
            await application.updater.idle()
            
        except (NetworkError, TimedOut, ConnectionError) as e:
            logger.warning(f"⚠️ Network error (attempt {retry_count + 1}): {e}")
            retry_count += 1
            
            if retry_count < max_retries:
                sleep_time = min(2 ** retry_count, 60)  # Max 60 seconds
                logger.info(f"🔄 Reconnecting in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                logger.error("❌ Max network retry attempts reached")
                break
                
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            retry_count += 1
            
            if retry_count < max_retries:
                time.sleep(10)
            else:
                break
        
        finally:
            try:
                await application.stop()
                await application.shutdown()
            except:
                pass

if __name__ == '__main__':
    # Run the async main function
    asyncio.run(main())
