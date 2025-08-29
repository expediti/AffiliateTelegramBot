import logging
import re
import os
import threading
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, jsonify

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for Render health checks (Required by Render)
app = Flask(__name__)

@app.route('/')
def health():
    return jsonify({
        "status": "healthy",
        "service": "Amazon Affiliate Bot",
        "version": "1.0"
    })

@app.route('/health')
def health_check():
    return jsonify({
        "bot_status": "running",
        "affiliate_tag": AFFILIATE_TAG if 'AFFILIATE_TAG' in globals() else "not-set"
    })

# Bot Configuration (Environment Variables)
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))  # Render default port

logger.info(f"Bot starting with affiliate tag: {AFFILIATE_TAG}")
logger.info(f"Flask server will run on port: {PORT}")

def convert_amazon_link(url, affiliate_tag):
    """Convert Amazon URL to affiliate link"""
    try:
        # Extract ASIN from various Amazon URL formats
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
            # Create clean affiliate URL
            return f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
        
    except Exception as e:
        logger.error(f"Error converting Amazon link: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links in text to affiliate links"""
    if not text:
        return text
        
    # Amazon URL patterns
    amazon_patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]+/[^\s]+',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+'
    ]
    
    converted_text = text
    conversion_count = 0
    
    for pattern in amazon_patterns:
        urls = re.findall(pattern, text)
        for url in urls:
            converted_url = convert_amazon_link(url, affiliate_tag)
            if converted_url != url:
                converted_text = converted_text.replace(url, converted_url)
                conversion_count += 1
    
    logger.info(f"Converted {conversion_count} Amazon links")
    return converted_text

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        welcome_msg = f"""
🤖 **Amazon Affiliate Bot - LIVE**

✅ **Status**: Running on Render.com
✅ **Affiliate Tag**: {AFFILIATE_TAG}
✅ **Target Domain**: {SEARCH_URL}

**How to use:**
1. Send me any Amazon product link
2. I'll convert it to your affiliate link instantly
3. Perfect for deals and promotions!

**Example:**
Send: `https://amazon.in/dp/B08N5WRWNW`
Get: `https://amazon.in/dp/B08N5WRWNW?tag={AFFILIATE_TAG}`

🚀 **Ready to earn commissions!**
"""
        await update.message.reply_text(welcome_msg)
        logger.info(f"Start command executed for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Error processing start command. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message or not update.message.text:
            return
            
        user_text = update.message.text
        user_id = update.effective_user.id
        
        logger.info(f"Processing message from user {user_id}")
        
        # Convert Amazon links
        converted_text = convert_all_links(user_text, AFFILIATE_TAG)
        
        if converted_text != user_text:
            # Links were converted
            response = f"🔗 **Converted Links:**\n\n{converted_text}"
            await update.message.reply_text(response)
            
            # Forward to channel if configured
            if YOUR_CHANNEL_ID:
                try:
                    await context.bot.send_message(
                        chat_id=YOUR_CHANNEL_ID,
                        text=f"🔥 **New Deal:**\n\n{converted_text}\n\n📢 _Auto-converted by bot_"
                    )
                    await update.message.reply_text("✅ Also posted to your channel!")
                    logger.info(f"Message forwarded to channel {YOUR_CHANNEL_ID}")
                except Exception as e:
                    logger.error(f"Failed to forward to channel: {e}")
                    await update.message.reply_text("⚠️ Converted link but couldn't post to channel.")
        else:
            # No Amazon links found
            await update.message.reply_text("❌ No Amazon links detected. Send me an Amazon product URL to convert!")
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("❌ Error processing your message. Please try again.")

def run_flask_server():
    """Run Flask server for Render health checks"""
    try:
        logger.info(f"Starting Flask server on 0.0.0.0:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def main():
    """Main function to start the bot"""
    # Validate required environment variables
    if not TOKEN:
        logger.error("❌ TOKEN environment variable not set!")
        raise ValueError("Missing required TOKEN environment variable")
    
    logger.info("🚀 Starting Amazon Affiliate Bot...")
    logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
    logger.info(f"✅ Search URL: {SEARCH_URL}")
    logger.info(f"✅ Channel ID: {YOUR_CHANNEL_ID}")
    
    try:
        # Start Flask server in background thread
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        logger.info("✅ Flask health server started")
        
        # Give Flask time to start
        time.sleep(2)
        
        # Create Telegram application
        application = Application.builder().token(TOKEN).build()
        
        # Add command and message handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("✅ Bot handlers registered")
        logger.info("✅ Starting Telegram polling...")
        
        # Start bot with polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"❌ Critical error starting bot: {e}")
        raise

if __name__ == '__main__':
    main()
