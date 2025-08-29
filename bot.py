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

# Flask app for Render health checks
app = Flask(__name__)

@app.route('/')
def health():
    return jsonify({
        "status": "healthy",
        "service": "Amazon Affiliate Bot",
        "version": "1.0"
    })

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))

logger.info(f"Bot starting with affiliate tag: {AFFILIATE_TAG}")
logger.info(f"Target channel ID: {YOUR_CHANNEL_ID}")

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
            return f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
        
    except Exception as e:
        logger.error(f"Error converting Amazon link: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links in text to affiliate links"""
    if not text:
        return text, 0
        
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
    
    return converted_text, conversion_count

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        welcome_msg = f"""
🤖 **Amazon Affiliate Bot - LIVE**

✅ **Status**: Running and Auto-Forwarding
✅ **Affiliate Tag**: {AFFILIATE_TAG}
✅ **Target Channel**: {YOUR_CHANNEL_ID if YOUR_CHANNEL_ID else 'Not configured'}

**How it works:**
1. Send me any Amazon product link
2. I'll convert it to your affiliate link
3. **Automatically post it to your channel** 📢
4. You also get a confirmation here

**Example:**
Send: `https://amazon.in/dp/B08N5WRWNW`
→ Converts to: `https://amazon.in/dp/B08N5WRWNW?tag={AFFILIATE_TAG}`
→ **Auto-posts to your channel!**

🚀 **Ready to earn commissions automatically!**
"""
        await update.message.reply_text(welcome_msg)
        logger.info(f"Start command executed for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages and auto-forward to channel"""
    try:
        if not update.message or not update.message.text:
            return
            
        user_text = update.message.text
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "User"
        
        logger.info(f"Processing message from user {user_id}: {user_name}")
        
        # Convert Amazon links
        converted_text, conversion_count = convert_all_links(user_text, AFFILIATE_TAG)
        
        if conversion_count > 0:
            # Links were converted - send to channel first, then confirm to user
            
            if YOUR_CHANNEL_ID:
                try:
                    # Create channel post with converted links
                    channel_post = f"""
🔥 DEAL FAM ALERT! 🔥
🛒 Amazon Link: {converted_text}
⏰ Limited Time: 6 hours left!
Deal Fam Rating: ⭐⭐⭐⭐⭐
Save Yours - Don't miss out!

#DealFam #DailyDeals #AmazonDeals #FlipkartOffers
#ShoppingDeals #IndianDeals #SaveMoney

"""
                    
                    # Send to your channel
                    channel_message = await context.bot.send_message(
                        chat_id=YOUR_CHANNEL_ID,
                        text=channel_post
                    )
                    
                    logger.info(f"✅ Successfully posted to channel {YOUR_CHANNEL_ID}")
                    
                    # Confirm to user
                    user_confirmation = f"""
✅ **Success! Posted to Your Channel**

🔗 **Converted {conversion_count} Amazon link(s):**
{converted_text}

📢 **Channel Post**: Your deal is now live in your channel!
💰 **Earnings**: Ready to generate affiliate commissions!

*Keep sending more deals!* 🚀
"""
                    await update.message.reply_text(user_confirmation)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to post to channel {YOUR_CHANNEL_ID}: {e}")
                    # Still show user the converted links even if channel posting fails
                    await update.message.reply_text(f"""
⚠️ **Converted Links** (Channel posting failed):

{converted_text}

❌ **Channel Error**: {str(e)}
Please check if bot has admin rights in your channel.
""")
            else:
                # No channel configured
                await update.message.reply_text(f"""
🔗 **Converted Links:**
{converted_text}

⚠️ **No Channel Configured**: Add YOUR_CHANNEL_ID to environment variables to enable auto-posting.
""")
        else:
            # No Amazon links found
            await update.message.reply_text(f"""
❌ **No Amazon Links Detected**

Send me Amazon product URLs like:
• https://amazon.in/dp/XXXXXXXXXX
• https://amzn.to/XXXXXX
• https://a.co/XXXXXX

I'll convert them to your affiliate links and post to your channel automatically! 🚀
""")
            
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
    
    if not YOUR_CHANNEL_ID:
        logger.warning("⚠️ YOUR_CHANNEL_ID not set - channel posting disabled")
    
    logger.info("🚀 Starting Amazon Affiliate Bot...")
    logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
    logger.info(f"✅ Search URL: {SEARCH_URL}")
    logger.info(f"✅ Channel ID: {YOUR_CHANNEL_ID}")
    
    try:
        # Start Flask server in background thread
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        logger.info("✅ Flask health server started")
        
        time.sleep(2)
        
        # Create Telegram application
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
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
