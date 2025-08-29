import logging
import re
import os
import threading
import time
import urllib.parse
import asyncio
import sys
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TimedOut, BadRequest, Conflict
from flask import Flask, jsonify

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def health():
    return jsonify({
        "status": "healthy",
        "service": "Amazon Affiliate Bot",
        "version": "3.1"
    })

@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "bot_active": True,
        "affiliate_tag": AFFILIATE_TAG
    })

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))

logger.info(f"🚀 Bot starting with affiliate tag: {AFFILIATE_TAG}")

def convert_amazon_link(url, affiliate_tag):
    """Enhanced Amazon URL converter"""
    try:
        if 'amzn.to' in url or 'a.co' in url:
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={affiliate_tag}"
        
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})',
            r'/([A-Z0-9]{10})/?(?:\?|$)',
            r'/([A-Z0-9]{10})/[^/]*/?(?:\?|$)',
        ]
        
        asin = None
        for pattern in asin_patterns:
            match = re.search(pattern, path, re.IGNORECASE)
            if match:
                potential_asin = match.group(1)
                if len(potential_asin) == 10 and potential_asin.isalnum():
                    asin = potential_asin
                    break
        
        if asin:
            if 'tag' in query_params:
                del query_params['tag']
            query_params['tag'] = [affiliate_tag]
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            target_domain = domain if 'amazon' in domain else SEARCH_URL
            return f"https://{target_domain}/dp/{asin}?{new_query}"
        
        if 'amazon' in domain:
            if 'tag' in query_params:
                del query_params['tag']
            query_params['tag'] = [affiliate_tag]
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            return f"https://{domain}{path}?{new_query}"
        
    except Exception as e:
        logger.error(f"Error converting link: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links in text"""
    if not text:
        return text, 0
        
    amazon_patterns = [
        r'https?://(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*',
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+',
        r'(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*(?=\s|$|[\.\,\!\?\)])',
    ]
    
    converted_text = text
    conversion_count = 0
    
    all_amazon_links = []
    for pattern in amazon_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            url = match.group(0)
            url = re.sub(r'[.,;!?)\]]+$', '', url)
            if not url.startswith('http') and not ('amzn.to' in url or 'a.co' in url):
                url = 'https://' + url
            all_amazon_links.append(url)
    
    unique_links = list(dict.fromkeys(all_amazon_links))
    
    for original_url in unique_links:
        converted_url = convert_amazon_link(original_url, affiliate_tag)
        if converted_url != original_url:
            converted_text = converted_text.replace(original_url, converted_url)
            conversion_count += 1
    
    return converted_text, conversion_count

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        welcome_msg = f"""
🤖 **Amazon Affiliate Bot - ACTIVE**

✅ **Status**: Running & Converting Links
✅ **Affiliate Tag**: {AFFILIATE_TAG}
✅ **Channel**: {YOUR_CHANNEL_ID if YOUR_CHANNEL_ID else 'Not configured'}

**Supported Links:**
• https://amazon.in/dp/XXXXXXXXXX
• https://amzn.to/XXXXXX
• amazon.in/dp/XXXXXXXXXX (without https)

**How it works:**
1. Send me any Amazon link
2. I convert it to your affiliate link
3. Auto-post to your channel
4. You earn commissions!

🚀 **Ready to convert links!**
"""
        await update.message.reply_text(welcome_msg)
        logger.info(f"Start command executed for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages"""
    try:
        if not update.message or not update.message.text:
            return
            
        user_text = update.message.text
        user_id = update.effective_user.id
        
        logger.info(f"Processing message from user {user_id}")
        
        converted_text, conversion_count = convert_all_links(user_text, AFFILIATE_TAG)
        
        if conversion_count > 0:
            if YOUR_CHANNEL_ID:
                try:
                    channel_post = f"""
🔥 **DEAL ALERT!** 🔥

🛒 **Amazon Link:**
{converted_text}

⏰ **Limited Time** - Grab it now!
⭐ **Rating:** ⭐⭐⭐⭐⭐

#DealFam #AmazonDeals #SaveMoney #ShoppingDeals
"""
                    
                    await context.bot.send_message(
                        chat_id=YOUR_CHANNEL_ID,
                        text=channel_post
                    )
                    
                    confirmation = f"""
✅ **Success! {conversion_count} link(s) converted**

🔗 **Your affiliate links:**
{converted_text}

📢 **Status:** Posted to channel successfully!
💰 **Ready to earn commissions!**
"""
                    await update.message.reply_text(confirmation)
                    
                except Exception as e:
                    logger.error(f"Channel posting failed: {e}")
                    await update.message.reply_text(f"✅ Links converted but channel posting failed:\n{converted_text}")
            else:
                await update.message.reply_text(f"✅ Links converted:\n{converted_text}")
        else:
            await update.message.reply_text("""
❌ **No Amazon links detected**

**Supported formats:**
• https://amazon.in/dp/XXXXXXXXXX
• https://amzn.to/XXXXXX
• amazon.in/dp/XXXXXXXXXX

Send me any Amazon link to convert!
""")
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("❌ Error processing message. Please try again.")

def run_flask_server():
    """Run Flask server"""
    try:
        logger.info(f"Starting Flask server on port {PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def main():
    """Main function with conflict handling"""
    if not TOKEN:
        logger.error("❌ TOKEN environment variable not set!")
        return
    
    logger.info("🚀 Starting Amazon Affiliate Bot...")
    
    try:
        # Start Flask server
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        logger.info("✅ Flask server started")
        
        time.sleep(3)
        
        # Create application with conflict handling
        application = (Application.builder()
                     .token(TOKEN)
                     .connect_timeout(30.0)
                     .read_timeout(30.0)
                     .write_timeout(30.0)
                     .build())
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("✅ Handlers registered")
        logger.info("🤖 Starting polling...")
        
        # Start polling with conflict handling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # This clears any pending updates
            close_loop=False,
            timeout=30,
            bootstrap_retries=3
        )
        
    except Conflict as e:
        logger.error(f"❌ Bot conflict detected: {e}")
        logger.error("💡 Another instance is already running. Please stop other instances.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
