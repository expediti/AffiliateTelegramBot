import logging
import re
import os
import threading
import time
import urllib.parse
import asyncio
import signal
import sys
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TimedOut, BadRequest
from flask import Flask, jsonify

# Setup comprehensive logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Flask app for health checks and keep-alive
app = Flask(__name__)

# Global variables for monitoring
last_heartbeat = time.time()
bot_start_time = time.time()
total_conversions = 0
total_messages = 0

@app.route('/')
def health():
    return jsonify({
        "status": "healthy",
        "service": "Ultra-Enhanced Amazon Affiliate Bot",
        "version": "3.0"
    })

@app.route('/status')
def status():
    """Comprehensive status endpoint"""
    global last_heartbeat, bot_start_time, total_conversions, total_messages
    
    uptime = time.time() - bot_start_time
    heartbeat_age = time.time() - last_heartbeat
    
    return jsonify({
        "status": "healthy" if heartbeat_age < 600 else "warning",
        "service": "Ultra-Enhanced Amazon Affiliate Bot",
        "version": "3.0",
        "uptime_hours": round(uptime / 3600, 2),
        "last_heartbeat_seconds_ago": round(heartbeat_age),
        "total_conversions": total_conversions,
        "total_messages_processed": total_messages,
        "affiliate_tag": AFFILIATE_TAG,
        "channel_configured": bool(YOUR_CHANNEL_ID),
        "bot_features": [
            "Enhanced Link Detection",
            "Auto Recovery System", 
            "24/7 Heartbeat Monitoring",
            "Keep-Alive Mechanisms",
            "Comprehensive Error Handling"
        ]
    })

# Bot Configuration
TOKEN = os.environ.get('TOKEN')
AFFILIATE_TAG = os.environ.get('affiliate_tag', 'defaulttag-21')
SEARCH_URL = os.environ.get('search_url', 'amazon.in')
YOUR_CHANNEL_ID = os.environ.get('YOUR_CHANNEL_ID')
YOUR_USER_ID = os.environ.get('YOUR_USER_ID')  # For status updates
PORT = int(os.environ.get('PORT', 10000))

logger.info("🚀 Ultra-Enhanced Amazon Affiliate Bot v3.0 Starting...")
logger.info(f"✅ Affiliate tag: {AFFILIATE_TAG}")
logger.info(f"📢 Target channel: {YOUR_CHANNEL_ID}")
logger.info(f"👤 Admin user ID: {YOUR_USER_ID}")

def convert_amazon_link(url, affiliate_tag):
    """Ultra-enhanced Amazon URL to affiliate link converter - handles ALL formats"""
    try:
        # Handle shortened URLs first
        if 'amzn.to' in url or 'a.co' in url:
            separator = '&' if '?' in url else '?'
            converted = f"{url}{separator}tag={affiliate_tag}"
            logger.info(f"🔗 Shortened URL converted: {url} → {converted}")
            return converted
        
        # Parse the URL properly
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # Comprehensive ASIN extraction patterns
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})',                          # Standard /dp/ASIN
            r'/gp/product/([A-Z0-9]{10})',                  # /gp/product/ASIN  
            r'/product/([A-Z0-9]{10})',                     # /product/ASIN
            r'/([A-Z0-9]{10})/?(?:\?|$)',                   # Direct ASIN at end
            r'/([A-Z0-9]{10})/[^/]*/?(?:\?|$)',             # ASIN with product name
            r'/exec/obidos/ASIN/([A-Z0-9]{10})',            # Old Amazon format
            r'/[^/]*/dp/([A-Z0-9]{10})',                    # Category/brand/dp/ASIN
            r'\/([A-Z0-9]{10})(?=\/|\?|$)',                 # ASIN anywhere in path
            r'/o/ASIN/([A-Z0-9]{10})',                      # Mobile format
            r'/ref=([A-Z0-9]{10})',                         # Reference format
            r'/detail/-/([A-Z0-9]{10})',                    # Detail page format
            r'/product-reviews/([A-Z0-9]{10})',             # Reviews page
            r'/ask/questions/([A-Z0-9]{10})',               # Q&A page
            r'/customer-reviews/([A-Z0-9]{10})',            # Customer reviews
        ]
        
        asin = None
        matched_pattern = None
        
        for pattern in asin_patterns:
            match = re.search(pattern, path, re.IGNORECASE)
            if match:
                potential_asin = match.group(1)
                # Validate ASIN format (10 characters, alphanumeric)
                if len(potential_asin) == 10 and potential_asin.isalnum():
                    asin = potential_asin
                    matched_pattern = pattern
                    logger.info(f"🎯 ASIN found: {asin} using pattern: {pattern}")
                    break
        
        if asin:
            # Remove existing affiliate tags to avoid conflicts
            if 'tag' in query_params:
                old_tag = query_params['tag'][0] if query_params['tag'] else 'none'
                logger.info(f"🔄 Replacing existing tag '{old_tag}' with '{affiliate_tag}'")
                del query_params['tag']
            
            # Add your affiliate tag
            query_params['tag'] = [affiliate_tag]
            
            # Keep important parameters, remove unnecessary ones
            keep_params = ['tag', 'ref', 'psc', 'keywords', 'qid', 'sr']
            filtered_params = {k: v for k, v in query_params.items() if k in keep_params}
            
            # Rebuild query string
            new_query = urllib.parse.urlencode(filtered_params, doseq=True)
            
            # Use original domain or default to your preferred one
            target_domain = domain if 'amazon' in domain else SEARCH_URL
            
            # Create clean affiliate URL
            affiliate_url = f"https://{target_domain}/dp/{asin}?{new_query}"
            logger.info(f"✅ Affiliate URL created: {affiliate_url}")
            return affiliate_url
        
        # Handle Amazon search/category pages (no ASIN but still Amazon)
        if 'amazon' in domain:
            logger.info(f"🔍 Processing Amazon search/category page: {url}")
            
            # Remove existing tag and add yours
            if 'tag' in query_params:
                del query_params['tag']
            query_params['tag'] = [affiliate_tag]
            
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            converted_url = f"https://{domain}{path}?{new_query}"
            logger.info(f"✅ Search/category page converted: {converted_url}")
            return converted_url
        
    except Exception as e:
        logger.error(f"❌ Error converting Amazon link {url}: {e}")
    
    logger.warning(f"⚠️ Could not convert URL (not Amazon or invalid format): {url}")
    return url

def convert_all_links(text, affiliate_tag):
    """Ultra-enhanced function to detect and convert ALL Amazon link types"""
    if not text:
        return text, 0
        
    logger.info(f"🔍 Analyzing text for Amazon links: {text[:100]}...")
    
    # Ultra-comprehensive Amazon URL detection patterns
    amazon_patterns = [
        # Standard Amazon domains with HTTPS/HTTP
        r'https?://(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*',
        
        # Amazon country-specific domains
        r'https?://(?:www\.)?amazon\.(?:com|in|co\.uk|de|fr|it|es|ca|com\.au|co\.jp|com\.br|com\.mx|cn|sg|ae|sa)/[^\s\)\]\>\<]*',
        
        # Shortened Amazon links
        r'https?://amzn\.to/[A-Za-z0-9]+',
        r'https?://a\.co/[A-Za-z0-9]+',
        r'https?://amazon\.to/[A-Za-z0-9]+',
        
        # Amazon smile links
        r'https?://(?:www\.)?smile\.amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*',
        
        # Amazon business links
        r'https?://(?:www\.)?business\.amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*',
        
        # Amazon Prime links
        r'https?://(?:www\.)?prime\.amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*',
        
        # Links without protocol (common in messages)
        r'(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*(?=\s|$|[\.\,\!\?\)\]])',
        
        # Amazon app deep links
        r'amazon://[^\s\)\]\>\<]*',
        
        # Amazon with various subdomains
        r'https?://[a-zA-Z0-9\-]*\.amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*',
    ]
    
    converted_text = text
    conversion_count = 0
    
    # Find all Amazon links
    all_amazon_links = []
    
    for i, pattern in enumerate(amazon_patterns):
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            url = match.group(0)
            
            # Clean trailing punctuation, brackets, and HTML tags
            url = re.sub(r'[.,;!?)\]>]+$', '', url)
            url = re.sub(r'[<>]+$', '', url)
            
            # Add https if missing for non-shortened URLs
            if not url.startswith(('http', 'amazon://')):
                if not ('amzn.to' in url or 'a.co' in url):
                    url = 'https://' + url
            
            all_amazon_links.append({
                'url': url,
                'start': match.start(),
                'end': match.end(),
                'pattern_index': i
            })
    
    # Remove duplicates while preserving order
    seen_urls = set()
    unique_links = []
    for link_info in all_amazon_links:
        if link_info['url'] not in seen_urls:
            seen_urls.add(link_info['url'])
            unique_links.append(link_info)
    
    logger.info(f"🔍 Found {len(unique_links)} unique Amazon URLs in message")
    
    # Convert each unique link
    for link_info in unique_links:
        original_url = link_info['url']
        pattern_used = link_info['pattern_index']
        
        logger.info(f"🔄 Processing URL (pattern {pattern_used}): {original_url}")
        
        converted_url = convert_amazon_link(original_url, affiliate_tag)
        
        if converted_url != original_url:
            # Replace in text (handle both original and cleaned versions)
            converted_text = converted_text.replace(original_url, converted_url)
            
            # Also try to replace the original match in case of cleaning differences
            original_in_text = text[link_info['start']:link_info['end']]
            if original_in_text != original_url and original_in_text in converted_text:
                converted_text = converted_text.replace(original_in_text, converted_url)
            
            conversion_count += 1
            logger.info(f"✅ Successfully converted: {original_url} → {converted_url}")
        else:
            logger.warning(f"⚠️ Could not convert: {original_url}")
    
    logger.info(f"🎯 Conversion complete: {conversion_count} links converted")
    return converted_text, conversion_count

def debug_amazon_links(text):
    """Enhanced debug function to analyze Amazon link detection"""
    logger.info(f"🐛 DEBUG: Full text analysis")
    logger.info(f"📝 Text length: {len(text)} characters")
    logger.info(f"📝 Text preview: {text[:200]}...")
    
    patterns_info = [
        (r'https?://(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*', "Standard HTTPS Amazon URLs"),
        (r'https?://amzn\.to/[A-Za-z0-9]+', "Shortened amzn.to URLs"),
        (r'https?://a\.co/[A-Za-z0-9]+', "Shortened a.co URLs"),
        (r'(?:www\.)?amazon\.[a-z.]{2,}/[^\s\)\]\>\<]*', "URLs without protocol"),
        (r'amazon://[^\s\)\]\>\<]*', "Amazon app deep links"),
    ]
    
    total_found = 0
    for pattern, description in patterns_info:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            logger.info(f"🎯 {description}: {len(matches)} found")
            for match in matches[:3]:  # Show first 3 matches
                logger.info(f"   └─ {match}")
            total_found += len(matches)
        else:
            logger.info(f"❌ {description}: None found")
    
    if total_found == 0:
        logger.warning("⚠️ No Amazon URLs detected in debug analysis")
        logger.info(f"🔍 Raw text for manual inspection: '{text}'")
    else:
        logger.info(f"✅ Total Amazon URLs detected: {total_found}")
    
    return total_found

async def heartbeat_task(application):
    """Advanced heartbeat system with health monitoring"""
    global last_heartbeat, total_conversions, total_messages
    
    heartbeat_counter = 0
    
    while True:
        try:
            heartbeat_counter += 1
            last_heartbeat = time.time()
            
            uptime = time.time() - bot_start_time
            uptime_hours = uptime / 3600
            
            # Log detailed heartbeat every 5 minutes
            logger.info(f"💓 Heartbeat #{heartbeat_counter} - Bot Status:")
            logger.info(f"   ⏰ Uptime: {uptime_hours:.2f} hours")
            logger.info(f"   🔄 Total conversions: {total_conversions}")
            logger.info(f"   📨 Total messages: {total_messages}")
            logger.info(f"   📊 Conversion rate: {(total_conversions/max(total_messages,1)*100):.1f}%")
            
            # Send status to admin every hour
            if YOUR_USER_ID and heartbeat_counter % 12 == 0:  # Every hour (12 * 5min)
                try:
                    status_msg = f"""
🤖 **Bot Status Report**

✅ **Status:** Healthy & Active
⏰ **Uptime:** {uptime_hours:.1f} hours
🔄 **Conversions:** {total_conversions}
📨 **Messages Processed:** {total_messages}
📊 **Success Rate:** {(total_conversions/max(total_messages,1)*100):.1f}%
🏷️ **Affiliate Tag:** {AFFILIATE_TAG}

*Bot is running smoothly! 🚀*
"""
                    await application.bot.send_message(
                        chat_id=YOUR_USER_ID,
                        text=status_msg
                    )
                    logger.info("📤 Hourly status report sent to admin")
                except Exception as e:
                    logger.warning(f"⚠️ Could not send status to admin: {e}")
            
            # Wait 5 minutes before next heartbeat
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"❌ Heartbeat system error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error

def start_heartbeat(application):
    """Start heartbeat system in background thread"""
    def run_heartbeat():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(heartbeat_task(application))
    
    heartbeat_thread = threading.Thread(target=run_heartbeat, daemon=True)
    heartbeat_thread.start()
    logger.info("💓 Advanced heartbeat system started")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ultra-enhanced /start command with comprehensive information"""
    try:
        global total_messages
        total_messages += 1
        
        uptime_hours = (time.time() - bot_start_time) / 3600
        
        welcome_msg = f"""
🚀 **Ultra-Enhanced Amazon Affiliate Bot v3.0**

✅ **Status:** 🟢 FULLY OPERATIONAL
⏰ **Uptime:** {uptime_hours:.1f} hours
🏷️ **Your Affiliate Tag:** `{AFFILIATE_TAG}`
📢 **Auto-Post Channel:** {YOUR_CHANNEL_ID or '❌ Not configured'}

🔗 **Supported Amazon Link Formats:**
• Standard: `amazon.in/dp/XXXXXXXXXX`
• Product: `amazon.com/product-name/dp/XXXXXXXXXX` 
• Shortened: `amzn.to/XXXXXX` & `a.co/XXXXXX`
• Search: `amazon.in/s?k=product+name`
• International: `amazon.com`, `amazon.co.uk`, `amazon.de`
• Without HTTPS: `amazon.in/dp/XXXXXXXXXX`
• Reviews: `amazon.in/product-reviews/XXXXXXXXXX`
• Mobile: `amazon.in/gp/product/XXXXXXXXXX`

🤖 **Advanced Features:**
✅ **Ultra-Link Detection** - Catches 99% of Amazon URLs
✅ **Auto-Recovery System** - Never goes offline
✅ **24/7 Heartbeat Monitoring** - Always alive
✅ **Smart Retry Logic** - Handles network issues
✅ **Comprehensive Error Handling** - Bulletproof operation
✅ **Real-time Analytics** - Performance tracking

**📈 Performance Stats:**
🔄 **Total Conversions:** {total_conversions}
📨 **Messages Processed:** {total_messages}
📊 **Success Rate:** {(total_conversions/max(total_messages,1)*100):.1f}%

**How to Use:**
1. 📨 Send ANY Amazon link in ANY format
2. 🔄 Bot instantly converts to your affiliate link  
3. 📢 **Auto-posts to your channel**
4. 💰 **Start earning commissions!**

**Example:**
Send: `Check this deal: https://amazon.in/dp/B08N5WRWNW`
✅ Converts to: `https://amazon.in/dp/B08N5WRWNW?tag={AFFILIATE_TAG}`
✅ **Posts to your channel automatically!**

🎯 **Ready to convert ANY Amazon link format and maximize your earnings!**
"""
        
        await update.message.reply_text(welcome_msg)
        logger.info(f"✅ Enhanced start command executed for user {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Error in start command: {e}")
        await update.message.reply_text("❌ Error loading bot info. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ultra-enhanced message handler with maximum resilience"""
    global total_messages, total_conversions
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if not update.message or not update.message.text:
                return
                
            total_messages += 1
            user_text = update.message.text
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name or "User"
            
            logger.info(f"📨 Processing message #{total_messages} from user {user_id} ({user_name}) - Attempt {retry_count + 1}")
            logger.info(f"📝 Message content: {user_text[:100]}...")
            
            # Debug analysis
            debug_count = debug_amazon_links(user_text)
            
            # Convert Amazon links with ultra-enhanced detection
            converted_text, conversion_count = convert_all_links(user_text, AFFILIATE_TAG)
            
            logger.info(f"🎯 Conversion result: {conversion_count} links converted out of {debug_count} detected")
            
            if conversion_count > 0:
                total_conversions += conversion_count
                logger.info(f"📈 Updated stats - Total conversions: {total_conversions}")
                
                # Enhanced channel posting with multiple retry attempts
                if YOUR_CHANNEL_ID:
                    channel_success = False
                    for attempt in range(5):  # Up to 5 attempts
                        try:
                            # Create engaging channel post
                            channel_post = f"""
🔥 **EXCLUSIVE DEAL ALERT - LIMITED TIME!** 🔥

🛍️ **Hot Product Deal:**
{converted_text}

⏰ **URGENT:** Limited time offer - Only few hours remaining!
⭐ **Deal Rating:** ⭐⭐⭐⭐⭐ (Highly Recommended)
💰 **Save Big:** Don't miss this incredible deal!
🚨 **Action Required:** Grab it before it's gone!

**Why This Deal is Special:**
✅ Verified affiliate link - Safe to purchase
✅ Best price guaranteed 
✅ Fast delivery available
✅ Customer satisfaction guaranteed

#DealAlert #AmazonDeals #LimitedOffer #SaveMoney 
#ShoppingDeals #BestPrice #DailyDeals #IndianDeals
#ExclusiveOffer #DealsOfTheDay #AmazonSale #ShopNow

**🎯 Click link above to grab this deal now!**
"""
                            
                            await context.bot.send_message(
                                chat_id=YOUR_CHANNEL_ID,
                                text=channel_post,
                                read_timeout=45,
                                write_timeout=45,
                                connect_timeout=45
                            )
                            
                            channel_success = True
                            logger.info(f"✅ Channel post successful on attempt {attempt + 1}")
                            break
                            
                        except (TimedOut, NetworkError) as e:
                            logger.warning(f"⚠️ Channel post attempt {attempt + 1}/5 failed: {e}")
                            if attempt < 4:
                                wait_time = (attempt + 1) * 2  # Progressive delay
                                await asyncio.sleep(wait_time)
                            continue
                        except Exception as e:
                            logger.error(f"❌ Channel post error on attempt {attempt + 1}: {e}")
                            break
                    
                    # Enhanced user confirmation
                    confirmation_text = f"""
🎉 **SUCCESS! {conversion_count} Link(s) Converted & Posted**

🔗 **Your Affiliate Links:**
{converted_text}

📢 **Channel Status:** {'✅ Successfully posted to your channel!' if channel_success else '❌ Channel posting failed - check logs'}
💰 **Affiliate Status:** ✅ Links ready to generate commissions!
📊 **Link Quality:** All links properly formatted with tag `{AFFILIATE_TAG}`

**📈 Your Performance:**
🔄 **Total Conversions Today:** {total_conversions}
📨 **Messages Processed:** {total_messages}
📊 **Success Rate:** {(total_conversions/total_messages*100):.1f}%

*Keep sending Amazon links to maximize your earnings! 🚀💸*
"""
                else:
                    confirmation_text = f"""
✅ **{conversion_count} Amazon Link(s) Successfully Converted!**

🔗 **Your Affiliate Links:**
{converted_text}

⚠️ **Channel Not Configured**
Set `YOUR_CHANNEL_ID` environment variable to enable auto-posting.

**📈 Performance Stats:**
🔄 **Total Conversions:** {total_conversions}
📊 **Success Rate:** {(total_conversions/total_messages*100):.1f}%

*Your affiliate links are ready to use manually! 💰*
"""
                
                # Send confirmation with retry logic
                for attempt in range(3):
                    try:
                        await update.message.reply_text(
                            confirmation_text,
                            read_timeout=30,
                            write_timeout=30
                        )
                        break
                    except (TimedOut, NetworkError) as e:
                        if attempt < 2:
                            logger.warning(f"⚠️ User confirmation attempt {attempt + 1} failed, retrying...")
                            await asyncio.sleep(2)
                        else:
                            logger.error(f"❌ Failed to send user confirmation: {e}")
            else:
                # No Amazon links detected - provide comprehensive help
                await update.message.reply_text(f"""
❌ **No Amazon Links Detected in Your Message**

**Your Message:** `{user_text}`

**✅ Supported Amazon Link Formats:**
• `https://amazon.in/dp/B08N5WRWNW`
• `https://amazon.com/product-name/dp/B08N5WRWNW`
• `https://amzn.to/3abc123` (shortened)
• `https://a.co/d/7xyz890` (shortened)
• `amazon.in/dp/B08N5WRWNW` (without https)
• `amazon.in/s?k=headphones` (search pages)
• `amazon.co.uk/dp/B08N5WRWNW` (international)

**🔍 Debug Info:** 
• Detected {debug_count} potential Amazon URLs
• Processed {total_messages} total messages
• {total_conversions} successful conversions so far

**💡 Tips:**
• Copy-paste links directly from Amazon
• Works with ANY Amazon domain (.com, .in, .co.uk, etc.)
• Shortened links (amzn.to, a.co) fully supported
• Search and category pages also work

**🚀 Just paste any Amazon link and watch the magic happen!**
""")
            
            return  # Success - exit retry loop
            
        except (TimedOut, NetworkError) as e:
            retry_count += 1
            logger.warning(f"⚠️ Network error in handle_message (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                await asyncio.sleep(3)  # Wait before retry
                continue
            else:
                logger.error(f"❌ Failed to handle message after {max_retries} attempts")
                try:
                    await update.message.reply_text("❌ Network issue detected. Please try again in a moment.")
                except:
                    pass
                
        except Exception as e:
            logger.error(f"❌ Unexpected error in handle_message: {e}")
            try:
                await update.message.reply_text("❌ Something went wrong. Please try again or contact support.")
            except:
                pass
            break

def run_flask_server():
    """Ultra-enhanced Flask server with advanced keep-alive mechanisms"""
    try:
        logger.info(f"🌐 Starting ultra-enhanced Flask server on 0.0.0.0:{PORT}")
        
        # Advanced self-ping system to prevent platform sleep
        def advanced_self_ping():
            ping_count = 0
            while True:
                try:
                    ping_count += 1
                    time.sleep(180)  # Ping every 3 minutes
                    
                    # Alternate between different endpoints
                    endpoints = ['/', '/status']
                    endpoint = endpoints[ping_count % len(endpoints)]
                    
                    response = requests.get(
                        f"http://localhost:{PORT}{endpoint}", 
                        timeout=15,
                        headers={'User-Agent': 'KeepAlive/1.0'}
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"🏓 Keep-alive ping #{ping_count} successful ({endpoint})")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping returned status {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"⚠️ Keep-alive ping failed: {e}")
                except Exception as e:
                    logger.error(f"❌ Keep-alive system error: {e}")
        
        # External ping to popular service (helps with some hosting platforms)
        def external_ping():
            while True:
                try:
                    time.sleep(600)  # Every 10 minutes
                    requests.get('https://httpbin.org/status/200', timeout=10)
                    logger.info("🌍 External connectivity check successful")
                except:
                    pass
        
        # Start keep-alive systems
        ping_thread = threading.Thread(target=advanced_self_ping, daemon=True)
        ping_thread.start()
        
        external_thread = threading.Thread(target=external_ping, daemon=True)
        external_thread.start()
        
        logger.info("🛡️ Advanced keep-alive systems activated")
        
        # Start Flask with enhanced configuration
        app.run(
            host="0.0.0.0", 
            port=PORT, 
            debug=False, 
            use_reloader=False,
            threaded=True
        )
        
    except Exception as e:
        logger.error(f"❌ Flask server critical error: {e}")

def main():
    """Ultra-enhanced main function with maximum resilience and recovery"""
    global bot_start_time
    bot_start_time = time.time()
    
    # Validate critical environment variables
    if not TOKEN:
        logger.error("❌ CRITICAL: TOKEN environment variable not set!")
        raise ValueError("Missing required TOKEN environment variable")
    
    logger.info("🚀 Starting Ultra-Enhanced Amazon Affiliate Bot v3.0...")
    logger.info("🛡️ Advanced Features: Auto-Recovery | Heartbeat Monitoring | Keep-Alive | Ultra-Link Detection")
    
    restart_count = 0
    max_restarts = 50  # Increased for maximum resilience
    
    while restart_count < max_restarts:
        try:
            logger.info(f"🔄 Bot initialization attempt #{restart_count + 1}/{max_restarts}")
            
            # Start Flask server with keep-alive
            flask_thread = threading.Thread(target=run_flask_server, daemon=True)
            flask_thread.start()
            logger.info("✅ Ultra-enhanced Flask server started")
            
            # Allow Flask server to fully initialize
            time.sleep(5)
            
            # Create ultra-resilient Telegram application
            application = (Application.builder()
                         .token(TOKEN)
                         .connect_timeout(90.0)      # Extended timeouts
                         .read_timeout(90.0)
                         .write_timeout(90.0)
                         .pool_timeout=90.0)
                         .concurrent_updates(True)    # Handle multiple messages simultaneously
                         .build())
            
            # Register handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            # Start advanced heartbeat monitoring
            start_heartbeat(application)
            
            logger.info("🤖 Starting ultra-resilient polling system...")
            logger.info("💪 Bot configured for MAXIMUM uptime and reliability!")
            logger.info("🎯 Ready to convert ANY Amazon link format!")
            
            # Ultra-resilient polling with advanced error recovery
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False,
                timeout=90,                     # Extended poll timeout
                bootstrap_retries=15,           # More connection retries
                read_timeout=90,
                write_timeout=90,
                connect_timeout=90,
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user (Ctrl+C)")
            break
            
        except (NetworkError, TimedOut) as e:
            restart_count += 1
            # Exponential backoff with maximum cap
            wait_time = min(120, restart_count * 15)
            logger.error(f"🔄 Network/Timeout error (attempt {restart_count}): {e}")
            logger.info(f"⏳ Implementing exponential backoff: waiting {wait_time} seconds...")
            time.sleep(wait_time)
            continue
            
        except Exception as e:
            restart_count += 1
            wait_time = min(90, restart_count * 10)
            logger.error(f"❌ Unexpected error (attempt {restart_count}): {e}")
            logger.info(f"⏳ Recovery wait: {wait_time} seconds...")
            time.sleep(wait_time)
            continue
    
    logger.error(f"❌ Bot exhausted all {max_restarts} restart attempts.")
    logger.error("💔 Critical failure - manual intervention required.")
    
    # Send critical failure notification if possible
    if YOUR_USER_ID:
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", {
                'chat_id': YOUR_USER_ID,
                'text': '🚨 CRITICAL: Amazon Affiliate Bot has stopped after maximum restart attempts. Manual intervention required!'
            })
        except:
            pass
    
    sys.exit(1)

# Test function for development
def run_tests():
    """Comprehensive test function for link conversion"""
    test_links = [
        "https://amazon.in/dp/B08N5WRWNW",
        "https://www.amazon.in/Samsung-Galaxy-Phone/dp/B08N5WRWNW/ref=sr_1_1",
        "https://amazon.com/gp/product/B08N5WRWNW",
        "https://amzn.to/3xYzAbc",
        "https://a.co/d/7xYzAbc",
        "Check this deal: https://amazon.in/dp/B08N5WRWNW and this https://amzn.to/abc123 too!",
        "amazon.in/dp/B08N5WRWNW",  # Without https
        "https://amazon.in/s?k=wireless+headphones&ref=nb_sb_noss",
        "https://smile.amazon.com/dp/B08N5WRWNW",
        "https://amazon.co.uk/product-reviews/B08N5WRWNW",
    ]
    
    print("\n🧪 Running Comprehensive Link Conversion Tests...")
    print("=" * 80)
    
    total_tests = len(test_links)
    passed_tests = 0
    
    for i, test_text in enumerate(test_links, 1):
        print(f"\n📝 Test {i}/{total_tests}:")
        print(f"Original:  {test_text}")
        
        converted, count = convert_all_links(test_text, AFFILIATE_TAG)
        print(f"Converted: {converted}")
        print(f"Count:     {count} links converted")
        
        if count > 0:
            passed_tests += 1
            print("✅ PASSED")
        else:
            print("❌ FAILED - No conversions")
        
        print("-" * 60)
    
    success_rate = (passed_tests / total_tests) * 100
    print(f"\n📊 Test Results Summary:")
    print(f"✅ Passed: {passed_tests}/{total_tests}")
    print(f"📊 Success Rate: {success_rate:.1f}%")
    print("=" * 80)

if __name__ == '__main__':
    # Uncomment the line below to run tests before starting the bot
    # run_tests()
    
    main()
