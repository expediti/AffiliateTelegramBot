import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread
import time

# Flask app for Render health check
app = Flask(__name__)

@app.route('/')
def health():
    return "🤖 Amazon Affiliate Bot is running!"

@app.route('/status')
def status():
    return {
        "status": "running",
        "affiliate_tag": AFFILIATE_TAG,
        "uptime": "OK"
    }

# Configuration
TOKEN = os.getenv('TOKEN')
AFFILIATE_TAG = os.getenv('affiliate_tag', 'yourname-21')
SEARCH_URL = os.getenv('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.getenv('YOUR_CHANNEL_ID', '-1001234567890')

# Deal detection keywords
DEAL_KEYWORDS = ['deal', 'offer', 'discount', 'sale', '₹', 'rs', 'price', 'off', '%', 'cashback', 'coupon']

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
    """Convert all Amazon and Flipkart links in text"""
    # Amazon URL patterns
    amazon_patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]+/.*?(?=\s|$)',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+'
    ]
    
    converted_text = text
    
    # Convert Amazon links
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
✅ Forward deals automatically  
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
            
            # Forward to your channel if configured
            if YOUR_CHANNEL_ID and YOUR_CHANNEL_ID != '-1001234567890':
                try:
                    forward_text = f"🔥 **Deal Alert!**\n\n{converted_text}\n\n📢 Auto-forwarded by bot"
                    await context.bot.send_message(chat_id=YOUR_CHANNEL_ID, text=forward_text)
                    await message.reply_text("✅ Also posted to your channel!")
                except Exception as e:
                    logger.error(f"Error forwarding to channel: {e}")
        else:
            await message.reply_text("❌ No Amazon links found to convert. Send me an Amazon product URL!")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await message.reply_text("❌ Error processing your message. Please try again.")

def run_flask():
    """Run Flask server for Render health check"""
    try:
        port = int(os.environ.get("PORT", 8000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def main():
    """Start the bot and Flask server"""
    logger.info("Starting Amazon Affiliate Bot...")
    
    if not TOKEN:
        logger.error("❌ No TOKEN provided! Add your bot token to environment variables.")
        return
    
    # Start Flask server in background thread for health checks
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask health server started")
    
    # Create telegram application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("✅ Starting Telegram bot...")
    logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
    logger.info(f"✅ Target channel: {YOUR_CHANNEL_ID}")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ Bot startup error: {e}")

if __name__ == '__main__':
    main()
