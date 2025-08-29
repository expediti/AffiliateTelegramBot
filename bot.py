import logging
import re
import os
import time
import threading
import asyncio
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
        "version": "4.0"
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
    """Convert Amazon URL to affiliate link - ENHANCED VERSION"""
    try:
        # Comprehensive ASIN extraction patterns
        patterns = [
            r'/dp/([A-Z0-9]{10})',                    # Standard /dp/ format
            r'/gp/product/([A-Z0-9]{10})',           # /gp/product/ format  
            r'/product/([A-Z0-9]{10})',              # /product/ format
            r'/exec/obidos/ASIN/([A-Z0-9]{10})',     # Old format
            r'/o/ASIN/([A-Z0-9]{10})',               # Another old format
            r'[?&]ASIN=([A-Z0-9]{10})',              # ASIN parameter
            r'/([A-Z0-9]{10})(?:[/?]|$)',            # Direct ASIN in path
        ]
        
        asin = None
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                asin = match.group(1)
                logger.info(f"✅ ASIN found: {asin}")
                break
        
        if asin:
            # Clean affiliate URL
            affiliate_url = f"https://{SEARCH_URL}/dp/{asin}?tag={affiliate_tag}"
            return affiliate_url
        else:
            logger.warning(f"❌ No ASIN found in URL: {url}")
            
    except Exception as e:
        logger.error(f"Link conversion error: {e}")
    
    return url

def expand_short_url(short_url, max_redirects=5):
    """Expand shortened URLs to get the final Amazon URL"""
    try:
        response = requests.head(short_url, allow_redirects=True, timeout=10)
        final_url = response.url
        logger.info(f"🔗 Expanded {short_url} → {final_url}")
        return final_url
    except Exception as e:
        logger.warning(f"⚠️ Failed to expand {short_url}: {e}")
        return short_url

def convert_all_links(text, affiliate_tag):
    """Convert all Amazon links - COMPREHENSIVE VERSION"""
    if not text:
        return text, 0
    
    # Enhanced Amazon URL patterns
    amazon_patterns = [
        # Standard Amazon domains
        r'https?://(?:www\.)?amazon\.[a-z.]+/[^\s]*',
        # Amazon short links
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+',
        # Amazon smile
        r'https?://smile\.amazon\.[a-z.]+/[^\s]*',
        # Amazon mobile links
        r'https?://(?:www\.)?amazon\.[a-z.]+/[^\s]*',
    ]
    
    converted_text = text
    conversion_count = 0
    processed_urls = set()  # Avoid duplicate processing
    
    # Find and convert all Amazon URLs
    for pattern in amazon_patterns:
        urls = re.findall(pattern, text, re.IGNORECASE)
        
        for url in urls:
            if url in processed_urls:
                continue
            processed_urls.add(url)
            
            original_url = url
            
            # Expand short URLs first
            if 'amzn.to' in url or 'a.co' in url:
                url = expand_short_url(url)
            
            # Convert to affiliate link
            converted_url = convert_amazon_link(url, affiliate_tag)
            
            if converted_url != original_url and converted_url != url:
                converted_text = converted_text.replace(original_url, converted_url)
                conversion_count += 1
                logger.info(f"✅ Converted: {original_url} → {converted_url}")
            else:
                logger.info(f"⚠️ Could not convert: {original_url}")
    
    logger.info(f"📊 Total conversions: {conversion_count}")
    return converted_text, conversion_count

def keepalive_ping():
    """Ping server every 14 minutes to prevent sleep"""
    while True:
        try:
            if KEEPALIVE_URL:
                response = requests.get(f"{KEEPALIVE_URL}/keepalive", timeout=30)
                logger.info(f"💓 Keepalive ping: {response.status_code}")
            else:
                logger.info("💓 Keepalive heartbeat")
        except Exception as e:
            logger.warning(f"⚠️ Keepalive failed: {e}")
        
        time.sleep(KEEPALIVE_INTERVAL)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command"""
    welcome_msg = f"""
🤖 **24/7 Amazon Affiliate Bot v4.0**

✅ **Status**: Always Online (Never Sleeps)
✅ **Uptime**: 24/7 Cloud Hosting  
✅ **Affiliate Tag**: `{AFFILIATE_TAG}`
✅ **Domain**: `{SEARCH_URL}`
✅ **Auto-Keepalive**: ENABLED

**🔥 ENHANCED FEATURES:**
• Runs 24/7 even when your device is OFF
• Advanced Amazon link detection
• Short URL expansion (amzn.to, a.co)
• Network-resilient connection
• Auto-restart on failures
• Instant affiliate conversion

**💡 USAGE:**
Just send any Amazon link and I'll convert it instantly!

**🔗 SUPPORTED FORMATS:**
• `amazon.com/dp/XXXXXXXXXX`
• `amazon.in/gp/product/XXXXXXXXXX`  
• `amzn.to/XXXXXX`
• `a.co/XXXXXX`
• `smile.amazon.com/dp/XXXXXXXXXX`
• And many more variations!

**🚀 Your bot works 24/7 independently!**
"""
    
    await safe_send(context.bot, update.message.chat_id, welcome_msg)

async def safe_send(bot, chat_id, text, max_retries=3):
    """Send message with enhanced retry logic"""
    for attempt in range(max_retries):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except (NetworkError, TimedOut) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                logger.warning(f"🔄 Retry {attempt + 1} in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Failed after {max_retries} attempts: {e}")
                # Try without markdown as fallback
                try:
                    return await bot.send_message(chat_id=chat_id, text=text)
                except:
                    raise
        except RetryAfter as e:
            logger.warning(f"⏳ Rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.error(f"💥 Unexpected error: {e}")
            if attempt == max_retries - 1:
                # Final attempt without markdown
                try:
                    return await bot.send_message(chat_id=chat_id, text=text)
                except:
                    raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced message handler with full Amazon link support"""
    try:
        text = update.message.text
        user_name = update.effective_user.first_name or "User"
        chat_id = update.message.chat_id
        
        logger.info(f"📨 Processing message from {user_name}")
        
        # Convert all Amazon links
        converted_text, conversion_count = convert_all_links(text, AFFILIATE_TAG)
        
        if conversion_count > 0:
            # Success - post to channel if configured
            if YOUR_CHANNEL_ID:
                try:
                    channel_message = f"""
🔥 **DEAL ALERT - 24/7 BOT**

{converted_text}

💰 **Affiliate Ready** | 📱 **Shared by**: {user_name}
🤖 **Always-On Bot** | ⚡ **Grab Now!**
"""
                    
                    await safe_send(context.bot, YOUR_CHANNEL_ID, channel_message)
                    
                    # Confirmation to user
                    confirmation = f"""
✅ **SUCCESS - Links Converted!**

🔗 **Your Affiliate Links:**
{converted_text}

📊 **Conversion Stats:**
• Links converted: **{conversion_count}**
• Posted to channel: ✅
• Bot status: **24/7 Online**
• Affiliate tag: `{AFFILIATE_TAG}`

💰 **Ready to earn commissions!**
"""
                    await safe_send(context.bot, chat_id, confirmation)
                    
                except Exception as e:
                    logger.error(f"Channel posting error: {e}")
                    # Send converted links anyway
                    await safe_send(context.bot, chat_id, f"✅ **Converted Links:**\n\n{converted_text}")
            else:
                # No channel configured, just return converted links
                result_msg = f"""
✅ **Amazon Links Converted!**

🔗 **Your Affiliate Links:**
{converted_text}

📊 **Stats:** {conversion_count} links converted
🏷️ **Tag:** `{AFFILIATE_TAG}`
"""
                await safe_send(context.bot, chat_id, result_msg)
        else:
            # No Amazon links found - helpful message
            help_msg = f"""
❌ **No Amazon Links Detected**

**💡 I can convert these Amazon link formats:**

**Standard Links:**
• `https://amazon.com/dp/B08XXXXX`
• `https://amazon.in/gp/product/B08XXXXX`
• `https://www.amazon.co.uk/dp/B08XXXXX`

**Short Links:**
• `https://amzn.to/3XXXXX`
• `https://a.co/d/XXXXX`

**Other Formats:**
• Amazon Smile links
• Mobile Amazon links
• International Amazon domains

**📝 Example Message:**
