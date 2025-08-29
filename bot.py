import logging
import re
import os
import threading
import time
import urllib.parse
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
        "service": "Enhanced Amazon Affiliate Bot",
        "version": "2.0"
    })

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
PORT = int(os.environ.get('PORT', 10000))

logger.info(f"🚀 Enhanced Bot starting with affiliate tag: {AFFILIATE_TAG}")
logger.info(f"📢 Target channel ID: {YOUR_CHANNEL_ID}")

def convert_amazon_link(url, affiliate_tag):
    """Enhanced Amazon URL to affiliate link converter - handles ALL formats"""
    try:
        # Handle shortened URLs first
        if 'amzn.to' in url or 'a.co' in url:
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={affiliate_tag}"
        
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # Extract ASIN using comprehensive patterns
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})',                    # Standard /dp/ASIN
            r'/gp/product/([A-Z0-9]{10})',            # /gp/product/ASIN  
            r'/product/([A-Z0-9]{10})',               # /product/ASIN
            r'/([A-Z0-9]{10})/?(?:\?|$)',             # Direct ASIN at end
            r'/([A-Z0-9]{10})/[^/]*/?(?:\?|$)',       # ASIN with product name
            r'/exec/obidos/ASIN/([A-Z0-9]{10})',      # Old Amazon format
            r'/[^/]*/dp/([A-Z0-9]{10})',              # Category/brand/dp/ASIN
            r'\/([A-Z0-9]{10})(?=\/|\?|$)',           # ASIN anywhere in path
        ]
        
        asin = None
        for pattern in asin_patterns:
            match = re.search(pattern, path)
            if match:
                potential_asin = match.group(1)
                # Validate ASIN format (10 characters, alphanumeric, starts with letter or number)
                if len(potential_asin) == 10 and potential_asin.isalnum():
                    asin = potential_asin
                    logger.info(f"🔍 ASIN found: {asin} using pattern: {pattern}")
                    break
        
        if asin:
            # Remove existing affiliate tags to avoid conflicts
            if 'tag' in query_params:
                del query_params['tag']
            
            # Add your affiliate tag
            query_params['tag'] = [affiliate_tag]
            
            # Rebuild query string
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            
            # Use original domain or default to your preferred one
            target_domain = domain if 'amazon' in domain else SEARCH_URL
            
            # Create clean affiliate URL
            affiliate_url = f"https://{target_domain}/dp/{asin}?{new_query}"
            logger.info(f"✅ Created affiliate URL: {affiliate_url}")
            return affiliate_url
        
        # Handle Amazon search/category pages (no ASIN but still Amazon)
        if 'amazon' in domain:
            # Remove existing tag and add yours
            if 'tag' in query_params:
                del query_params['tag']
            query_params['tag'] = [affiliate_tag]
            
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            return f"https://{domain}{path}?{new_query}"
        
    except Exception as e:
        logger.error(f"❌ Error converting Amazon link {url}: {e}")
    
    return url

def convert_all_links(text, affiliate_tag):
    """Enhanced function to detect and convert ALL Amazon link types"""
    if not text:
        return text, 0
        
    # Comprehensive Amazon URL detection patterns
    amazon_patterns = [
        # Standard Amazon domains with HTTPS
        r'https?://(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*',
        
        # Amazon country-specific domains
        r'https?://(?:www\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|ca|com\.au|co\.jp|com\.br|com\.mx)/[^\s\)\]]*',
        
        # Shortened Amazon links
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+',
        
        # Amazon smile links
        r'https?://(?:www\.)?smile\.amazon\.[a-z.]{2,}/[^\s\)\]]*',
        
        # Amazon business links
        r'https?://(?:www\.)?business\.amazon\.[a-z.]{2,}/[^\s\)\]]*',
        
        # Links without protocol (common in messages)
        r'(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*(?=\s|$|[\.\,\!\?\)])',
    ]
    
    converted_text = text
    conversion_count = 0
    
    # Find all Amazon links
    all_amazon_links = []
    
    for pattern in amazon_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            url = match.group(0)
            
            # Clean trailing punctuation and brackets
            url = re.sub(r'[.,;!?)\]]+$', '', url)
            
            # Add https if missing for non-shortened URLs
            if not url.startswith('http') and not ('amzn.to' in url or 'a.co' in url):
                url = 'https://' + url
            
            all_amazon_links.append((url, match.start(), match.end()))
    
    # Remove duplicates while preserving order and position
    seen = set()
    unique_links = []
    for url, start, end in all_amazon_links:
        if url not in seen:
            seen.add(url)
            unique_links.append((url, start, end))
    
    logger.info(f"🔍 Found {len(unique_links)} unique Amazon URLs in message")
    
    # Convert each unique link (process in reverse order to maintain positions)
    for original_url, start, end in reversed(unique_links):
        logger.info(f"🔄 Processing: {original_url}")
        
        converted_url = convert_amazon_link(original_url, affiliate_tag)
        
        if converted_url != original_url:
            # Replace in text
            converted_text = converted_text.replace(original_url, converted_url)
            conversion_count += 1
            logger.info(f"✅ Converted: {original_url} → {converted_url}")
        else:
            logger.warning(f"⚠️ Could not convert: {original_url}")
    
    return converted_text, conversion_count

def debug_amazon_links(text):
    """Debug function to analyze what Amazon links are detected"""
    logger.info(f"🔍 DEBUG: Analyzing text: {text[:100]}...")
    
    patterns = [
        (r'https?://(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*', "Standard Amazon URLs"),
        (r'https?://amzn\.to/[A-Za-z0-9]+', "Shortened amzn.to URLs"),
        (r'https?://a\.co/[A-Za-z0-9]+', "Shortened a.co URLs"),
        (r'(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]]*', "URLs without protocol"),
    ]
    
    total_found = 0
    for pattern, description in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            logger.info(f"📍 {description}: {len(matches)} found - {matches}")
            total_found += len(matches)
    
    if total_found == 0:
        logger.warning("❌ No Amazon URLs detected in debug analysis")
    else:
        logger.info(f"✅ Total Amazon URLs found: {total_found}")
    
    return total_found

def test_link_conversion():
    """Test function to verify link conversion works properly"""
    test_links = [
        "https://amazon.in/dp/B08N5WRWNW",
        "https://www.amazon.in/Samsung-Galaxy-Phone/dp/B08N5WRWNW/ref=sr_1_1",
        "https://amazon.com/gp/product/B08N5WRWNW",
        "https://amzn.to/3xYzAbc",
        "https://a.co/d/7xYzAbc",
        "Check this deal: https://amazon.in/dp/B08N5WRWNW and this https://amzn.to/abc123 too!",
        "amazon.in/dp/B08N5WRWNW",  # Without https
        "https://amazon.in/s?k=wireless+headphones&ref=nb_sb_noss",
    ]
    
    print("\n🧪 Testing Enhanced Link Conversion:")
    print("=" * 70)
    
    for i, test_text in enumerate(test_links, 1):
        print(f"\nTest {i}:")
        print(f"Original:  {test_text}")
        
        converted, count = convert_all_links(test_text, AFFILIATE_TAG)
        print(f"Converted: {converted}")
        print(f"Count:     {count} links converted")
        print("-" * 50)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced /start command with better information"""
    try:
        welcome_msg = f"""
🚀 **Enhanced Amazon Affiliate Bot v2.0 - LIVE**

✅ **Status**: Running & Auto-Converting ALL Amazon Links
✅ **Affiliate Tag**: `{AFFILIATE_TAG}`
✅ **Target Channel**: {YOUR_CHANNEL_ID if YOUR_CHANNEL_ID else '❌ Not configured'}

🔗 **Supported Link Types:**
• Standard: `amazon.in/dp/XXXXXXXXXX`
• Product pages: `amazon.com/product-name/dp/XXXXXXXXXX` 
• Shortened: `amzn.to/XXXXXX` & `a.co/XXXXXX`
• Search pages: `amazon.in/s?k=product+name`
• International: `amazon.com`, `amazon.co.uk`, etc.
• Without https: `amazon.in/dp/XXXXXXXXXX`

**How it works:**
1. 📨 Send ANY Amazon link in ANY format
2. 🔄 Bot converts it to your affiliate link  
3. 📢 **Auto-posts to your channel**
4. 💰 **You earn commissions!**

**Example:**
Send: `Check this https://amazon.in/dp/B08N5WRWNW deal!`
→ Converts to: `https://amazon.in/dp/B08N5WRWNW?tag={AFFILIATE_TAG}`
→ **Posts to channel automatically!**

🎯 **Ready to convert ANY Amazon link format!**
"""
        await update.message.reply_text(welcome_msg)
        logger.info(f"✅ Start command executed for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Error in start command: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced message handler with comprehensive link detection"""
    try:
        if not update.message or not update.message.text:
            return
            
        user_text = update.message.text
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "User"
        
        logger.info(f"📨 Processing message from user {user_id} ({user_name})")
        logger.info(f"📝 Original message: {user_text}")
        
        # Debug: Show what we detect
        debug_count = debug_amazon_links(user_text)
        
        # Convert Amazon links
        converted_text, conversion_count = convert_all_links(user_text, AFFILIATE_TAG)
        
        logger.info(f"🔄 Conversion result: {conversion_count} links converted")
        
        if conversion_count > 0:
            logger.info(f"✅ Final converted text: {converted_text}")
            
            # Post to channel if configured
            if YOUR_CHANNEL_ID:
                try:
                    # Enhanced channel post with better formatting
                    channel_post = f"""
🔥 **DEAL ALERT - LIMITED TIME!** 🔥

🛒 **Product Link:** 
{converted_text}

⏰ **Hurry!** Limited time offer - Only few hours left!
⭐ **Deal Rating:** ⭐⭐⭐⭐⭐
💰 **Save Big** - Don't miss this deal!

#DealFam #AmazonDeals #LimitedOffer #SaveMoney 
#ShoppingDeals #BestPrice #DailyDeals #IndianDeals
"""
                    
                    # Send to channel
                    channel_message = await context.bot.send_message(
                        chat_id=YOUR_CHANNEL_ID,
                        text=channel_post
                    )
                    
                    logger.info(f"✅ Successfully posted to channel {YOUR_CHANNEL_ID}")
                    
                    # Enhanced user confirmation
                    user_confirmation = f"""
🎉 **SUCCESS! Link(s) Converted & Posted**

🔗 **Converted {conversion_count} Amazon link(s):**
{converted_text}

📢 **Channel Status:** ✅ Posted to your channel successfully!
💰 **Affiliate Status:** ✅ Ready to generate commissions!
📊 **Link Quality:** All links properly formatted with your tag

*Send more Amazon links to keep earning!* 🚀💸
"""
                    await update.message.reply_text(user_confirmation)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to post to channel {YOUR_CHANNEL_ID}: {e}")
                    # Still show converted links even if channel posting fails
                    await update.message.reply_text(f"""
🔗 **Links Successfully Converted:**
{converted_text}

❌ **Channel Posting Failed:** {str(e)}
💡 **Solution:** Check if bot has admin rights in channel `{YOUR_CHANNEL_ID}`

*Your affiliate links are ready to use manually!*
""")
            else:
                # No channel configured
                await update.message.reply_text(f"""
✅ **Links Successfully Converted:**
{converted_text}

⚠️ **Channel Not Configured**
Add `YOUR_CHANNEL_ID` environment variable to enable auto-posting.

*Your affiliate links are ready to use!* 💰
""")
        else:
            # No Amazon links found - provide detailed help
            await update.message.reply_text(f"""
❌ **No Amazon Links Detected**

**Your message:** `{user_text}`

**✅ Supported formats (send any of these):**
• `https://amazon.in/dp/B08N5WRWNW`
• `https://amazon.com/product-name/dp/B08N5WRWNW`
• `https://amzn.to/3abc123` (shortened links)
• `https://a.co/d/7xyz890` (shortened links)
• `amazon.in/dp/B08N5WRWNW` (without https)
• `amazon.in/s?k=headphones` (search pages)

**🔍 Debug Info:** Found {debug_count} potential URLs in your message

**💡 Tip:** Just paste ANY Amazon link and I'll handle it! 🚀
""")
            
    except Exception as e:
        logger.error(f"❌ Error handling message: {e}")
        await update.message.reply_text("❌ Something went wrong processing your message. Please try again or contact support.")

def run_flask_server():
    """Run Flask server for health checks"""
    try:
        logger.info(f"🌐 Starting Flask health server on 0.0.0.0:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Flask server error: {e}")

def main():
    """Enhanced main function with better validation and testing"""
    # Validate required environment variables
    if not TOKEN:
        logger.error("❌ TOKEN environment variable not set!")
        raise ValueError("Missing required TOKEN environment variable")
    
    if not YOUR_CHANNEL_ID:
        logger.warning("⚠️ YOUR_CHANNEL_ID not set - channel posting disabled")
    
    logger.info("🚀 Starting Enhanced Amazon Affiliate Bot v2.0...")
    logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
    logger.info(f"✅ Search URL: {SEARCH_URL}")
    logger.info(f"✅ Channel ID: {YOUR_CHANNEL_ID}")
    
    # Run test conversion (uncomment for testing)
    # test_link_conversion()
    
    try:
        # Start Flask server in background
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        logger.info("✅ Flask health server started in background")
        
        # Small delay to ensure Flask starts
        time.sleep(2)
        
        # Create Telegram application
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("✅ Bot handlers registered successfully")
        logger.info("🤖 Starting Telegram bot polling...")
        logger.info("📱 Bot is now LIVE and ready to convert Amazon links!")
        
        # Start bot polling
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
