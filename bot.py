import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# Flask app for Render health check
app = Flask(__name__)

@app.route('/')
def health():
    return "🤖 Amazon Affiliate Bot is running!"

# Configuration
TOKEN = os.getenv('TOKEN')
AFFILIATE_TAG = os.getenv('affiliate_tag', 'yourname-21')
SEARCH_URL = os.getenv('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.getenv('YOUR_CHANNEL_ID', '-1001234567890')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_amazon_link(url, affiliate_tag):
    """Convert Amazon URL to affiliate link"""
    try:
        # Extract ASIN from URL
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if not asin_match:
            asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', url)
        
        if asin_match:
            asin = asin_match.group(1)
            affiliate_url = f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
            return affiliate_url
    except Exception as e:
        logger.error(f"Error converting link: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links in text"""
    amazon_patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]+/.*?(?=\s|$)',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+'
    ]
    
    converted_text = text
    
    for pattern in amazon_patterns:
        urls = re.findall(pattern, text)
        for url in urls:
            converted_url = convert_amazon_link(url, affiliate_tag)
            converted_text = converted_text.replace(url, converted_url)
    
    return converted_text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = f"""
🤖 **Amazon Affiliate Bot is Live!**

✅ Convert Amazon links to your affiliate links
✅ Running 24/7 on Render

**Your affiliate tag:** {AFFILIATE_TAG}

**Test it:** Send me any Amazon product link!

Example: https://amazon.in/dp/B08N5WRWNW
"""
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    try:
        message = update.message
        text = message.text
        
        if not text:
            return
        
        # Convert affiliate links
        converted_text = convert_all_links(text, AFFILIATE_TAG)
        
        if converted_text != text:
            response = f"🔗 **Converted Links:**\n\n{converted_text}"
            await message.reply_text(response)
            
            # Forward to channel if configured
            if YOUR_CHANNEL_ID and YOUR_CHANNEL_ID != '-1001234567890':
                try:
                    forward_text = f"🔥 **Deal Alert!**\n\n{converted_text}"
                    await context.bot.send_message(chat_id=YOUR_CHANNEL_ID, text=forward_text)
                    await message.reply_text("✅ Also posted to your channel!")
                except Exception as e:
                    logger.error(f"Error forwarding to channel: {e}")
        else:
            await message.reply_text("❌ No Amazon links found to convert.")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")

def run_flask():
    """Run Flask server for health check"""
    try:
        port = int(os.environ.get("PORT", 8000))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def main():
    """Start the bot"""
    if not TOKEN:
        logger.error("❌ No TOKEN provided!")
        return
    
    logger.info("🚀 Starting Amazon Affiliate Bot...")
    
    # Start Flask server in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask health server started")
    
    try:
        # Create application with error handling
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("✅ Bot handlers registered")
        logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
        
        # Start polling with error handling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Bot startup error: {e}")
        raise

if __name__ == '__main__':
    main()
