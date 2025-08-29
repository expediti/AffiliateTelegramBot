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
    return "🤖 Telegram Bot is running!"

@app.route('/health')
def health_check():
    return {"status": "Bot is active", "affiliate_tag": AFFILIATE_TAG}

# Configuration
TOKEN = os.getenv('TOKEN')
AFFILIATE_TAG = os.getenv('affiliate_tag', 'yourname-21')
SEARCH_URL = os.getenv('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.getenv('YOUR_CHANNEL_ID', '-1001234567890')

# Deal detection keywords
DEAL_KEYWORDS = ['deal', 'offer', 'discount', 'sale', '₹', 'rs', 'price', 'off', '%', 'cashback', 'coupon']

# Source channels to monitor
SOURCE_CHANNELS = [
    # -1001111111111,  # Replace with actual channel IDs
    # -1002222222222,  # Add more channel IDs here
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_amazon_link(url, affiliate_tag):
    """Convert Amazon URL to affiliate link"""
    try:
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

def is_deal_message(text):
    """Check if message contains deal-related keywords"""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in DEAL_KEYWORDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = f"""
🤖 **Amazon Affiliate Bot Active!**

✅ Convert Amazon/Flipkart links to your affiliate links
✅ Monitor channels for deals automatically  
✅ Forward deals to your channel

**Your affiliate tag:** {AFFILIATE_TAG}

Send me any Amazon link to test!
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
            await message.reply_text(f"🔗 **Converted Links:**\n\n{converted_text}")
            
            # Forward to your channel if configured
            if YOUR_CHANNEL_ID and YOUR_CHANNEL_ID != '-1001234567890':
                try:
                    forward_text = f"🔥 **Deal Alert!**\n\n{converted_text}"
                    await context.bot.send_message(chat_id=YOUR_CHANNEL_ID, text=forward_text)
                except Exception as e:
                    logger.error(f"Error forwarding to channel: {e}")
        else:
            await message.reply_text("No Amazon/Flipkart links found to convert.")
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")

def run_flask():
    """Run Flask server"""
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)

def main():
    """Start the bot"""
    if not TOKEN:
        logger.error("No TOKEN provided!")
        return
    
    # Start Flask server in background thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Create telegram application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("Bot started with health endpoint!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
