import os
import re
import logging
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
import json
from urllib.parse import urlparse, parse_qs, unquote
import sqlite3
from typing import Dict, List

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
AFFILIATE_TAG = os.getenv('AFFILIATE_TAG')
CHANNEL_ID = os.getenv('CHANNEL_ID')
BOT_ADMIN_ID = os.getenv('BOT_ADMIN_ID')

# Global variables for scheduling
scheduled_messages = {}
schedule_db = 'scheduled_messages.db'

# Amazon domains and patterns (same as before)
AMAZON_DOMAINS = [
    'amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 'amazon.it',
    'amazon.es', 'amazon.ca', 'amazon.com.au', 'amazon.co.jp', 'amazon.in',
    'amazon.com.br', 'amazon.com.mx', 'amazon.nl', 'amazon.se', 'amazon.sg'
]

AMAZON_PATTERNS = [
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/.*?/dp/([A-Z0-9]{10}))',
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/dp/([A-Z0-9]{10}))',
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/.*?/gp/product/([A-Z0-9]{10}))',
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/gp/aw/d/([A-Z0-9]{10}))',
    r'(https?://amzn\.to/[a-zA-Z0-9]+)',
    r'(https?://a\.co/[a-zA-Z0-9]+)',
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/s\?.*)',
    r'(https?://(?:www\.)?(?:' + '|'.join(re.escape(d) for d in AMAZON_DOMAINS) + r')/[^/\s]+/b/.*)',
]

# Database setup
def init_database():
    """Initialize SQLite database for scheduled messages"""
    conn = sqlite3.connect(schedule_db)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_links TEXT,
            affiliate_links TEXT,
            scheduled_time TEXT,
            message_content TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_scheduled_message(user_id, original_links, affiliate_links, scheduled_time, message_content):
    """Save scheduled message to database"""
    conn = sqlite3.connect(schedule_db)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scheduled_messages 
        (user_id, original_links, affiliate_links, scheduled_time, message_content)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, json.dumps(original_links), json.dumps(affiliate_links), 
          scheduled_time.isoformat(), message_content))
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id

def parse_schedule_time(user_input):
    """Parse user input time string to datetime object"""
    formats = [
        '%Y-%m-%d %H:%M',      # 2025-09-01 15:30
        '%d/%m/%Y %H:%M',      # 01/09/2025 15:30
        '%d-%m-%Y %H:%M',      # 01-09-2025 15:30
        '%Y-%m-%d %I:%M %p',   # 2025-09-01 03:30 PM
        '%d/%m/%Y %I:%M %p',   # 01/09/2025 03:30 PM
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(user_input, fmt)
            # Convert to UTC timezone
            dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None

# Previous helper functions (extract_all_amazon_links, get_asin_from_url, etc.) remain the same
def extract_all_amazon_links(text):
    """Extract all Amazon links from text"""
    found_links = []
    for pattern in AMAZON_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            found_links.append(match.group(1))
    return list(set(found_links))

def get_asin_from_url(url):
    """Extract ASIN from any Amazon URL"""
    asin_patterns = [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'/gp/aw/d/([A-Z0-9]{10})']
    for pattern in asin_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def resolve_short_url(url):
    """Resolve shortened Amazon URLs"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        return response.url
    except:
        return url

def create_affiliate_link(url, asin=None):
    """Create affiliate link from Amazon URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        if asin:
            affiliate_url = f"https://{domain}/dp/{asin}?tag={AFFILIATE_TAG}"
        else:
            if '?' in url:
                affiliate_url = f"{url}&tag={AFFILIATE_TAG}"
            else:
                affiliate_url = f"{url}?tag={AFFILIATE_TAG}"
        return affiliate_url
    except:
        return url

async def schedule_message_task(bot, message_id, scheduled_time, message_content, channel_id):
    """Background task to send scheduled message"""
    try:
        now = datetime.now(timezone.utc)
        delay = (scheduled_time - now).total_seconds()
        
        if delay > 0:
            await asyncio.sleep(delay)
        
        # Send to channel
        await bot.send_message(
            chat_id=channel_id,
            text=message_content,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )
        
        # Update database status
        conn = sqlite3.connect(schedule_db)
        cursor = conn.cursor()
        cursor.execute('UPDATE scheduled_messages SET status = ? WHERE id = ?', ('sent', message_id))
        conn.commit()
        conn.close()
        
        logging.info(f"Scheduled message {message_id} sent successfully")
        
    except Exception as e:
        logging.error(f"Error sending scheduled message {message_id}: {e}")
        # Update database status
        conn = sqlite3.connect(schedule_db)
        cursor = conn.cursor()
        cursor.execute('UPDATE scheduled_messages SET status = ? WHERE id = ?', ('failed', message_id))
        conn.commit()
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with scheduling info"""
    welcome_text = """
🤖 **Amazon Affiliate Link Converter & Scheduler Bot**

✅ **Features:**
• Converts ANY Amazon link to your affiliate link
• **🕐 Schedule posts for specific times**
• Automatically posts to your Telegram channel
• Supports all Amazon domains worldwide
• Handles product, search, and category links

📝 **How to use:**

**Instant Posting:**
• Send me any Amazon link(s) and they'll post immediately

**Scheduled Posting:**
• Use `/schedule` to schedule Amazon links for later
• Format: `/schedule 2025-09-01 15:30 [your Amazon links]`
• Supports multiple time formats

**Other Commands:**
• `/pending` - View pending scheduled messages
• `/cancel [id]` - Cancel scheduled message
• `/stats` - View bot statistics

🌍 **Supported:** All Amazon domains (US, UK, DE, IN, etc.)
    """
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /schedule command"""
    if len(context.args) < 3:
        help_text = """
📅 **Schedule Amazon Links**

**Usage:**
`/schedule YYYY-MM-DD HH:MM [Amazon links]`

**Examples:**
• `/schedule 2025-09-01 15:30 https://amazon.com/dp/B08N5WRWNW`
• `/schedule 01/09/2025 03:30 PM https://amzn.to/3xyz123`
• `/schedule 2025-12-25 09:00 [multiple Amazon links]`

**Supported Time Formats:**
• `2025-09-01 15:30` (24-hour)
• `01/09/2025 15:30` (DD/MM/YYYY)
• `2025-09-01 03:30 PM` (12-hour)
• `01/09/2025 03:30 PM`

**Features:**
• Schedule multiple links at once
• Automatic conversion to affiliate links
• Posts to your channel at exact time
• View pending with `/pending`
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Parse datetime from first two arguments
    date_part = context.args[0]
    time_part = context.args[1]
    datetime_str = f"{date_part} {time_part}"
    
    # Handle AM/PM if present
    if len(context.args) > 2 and context.args[2].upper() in ['AM', 'PM']:
        datetime_str += f" {context.args[2]}"
        links_text = " ".join(context.args[3:])
    else:
        links_text = " ".join(context.args[2:])
    
    scheduled_time = parse_schedule_time(datetime_str)
    
    if not scheduled_time:
        await update.message.reply_text(
            "❌ Invalid time format! Use: `/schedule 2025-09-01 15:30 [links]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if time is in the future
    if scheduled_time <= datetime.now(timezone.utc):
        await update.message.reply_text("❌ Please schedule for a future time!")
        return
    
    # Extract Amazon links
    amazon_links = extract_all_amazon_links(links_text)
    
    if not amazon_links:
        await update.message.reply_text("❌ No valid Amazon links found!")
        return
    
    # Process links and create message
    affiliate_links = []
    message_parts = []
    
    for original_url in amazon_links:
        try:
            # Resolve if shortened URL
            if 'amzn.to' in original_url or 'a.co' in original_url:
                resolved_url = resolve_short_url(original_url)
            else:
                resolved_url = original_url
            
            # Extract ASIN and create affiliate link
            asin = get_asin_from_url(resolved_url)
            affiliate_link = create_affiliate_link(resolved_url, asin)
            affiliate_links.append(affiliate_link)
            
            if asin:
                message_parts.append(f"🛒 **Amazon Product {asin}**\n🔗 **Shop Now:** {affiliate_link}")
            else:
                message_parts.append(f"🛒 **Amazon Deal**\n🔗 **Shop Now:** {affiliate_link}")
                
        except Exception as e:
            logging.error(f"Error processing link {original_url}: {e}")
    
    # Create final message content
    user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
    final_message = "\n\n".join(message_parts)
    final_message += f"\n\n📤 Scheduled by {user_mention}\n#Amazon #Deals #Scheduled"
    
    # Save to database
    message_id = save_scheduled_message(
        update.effective_user.id,
        amazon_links,
        affiliate_links,
        scheduled_time,
        final_message
    )
    
    # Create background task
    if CHANNEL_ID:
        asyncio.create_task(
            schedule_message_task(context.bot, message_id, scheduled_time, final_message, CHANNEL_ID)
        )
    
    # Confirm to user
    formatted_time = scheduled_time.strftime('%Y-%m-%d %H:%M UTC')
    confirmation = f"""
✅ **Scheduled Successfully!**

📅 **Time:** {formatted_time}
🔗 **Links:** {len(amazon_links)} Amazon link(s)
📬 **Message ID:** {message_id}

Your affiliate links will be posted to the channel at the scheduled time.

Use `/pending` to view all scheduled messages.
Use `/cancel {message_id}` to cancel this message.
    """
    await update.message.reply_text(confirmation, parse_mode=ParseMode.MARKDOWN)

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending scheduled messages"""
    conn = sqlite3.connect(schedule_db)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, scheduled_time, original_links, status 
        FROM scheduled_messages 
        WHERE user_id = ? AND status = 'pending'
        ORDER BY scheduled_time ASC
    ''', (update.effective_user.id,))
    
    pending_messages = cursor.fetchall()
    conn.close()
    
    if not pending_messages:
        await update.message.reply_text("📭 No pending scheduled messages!")
        return
    
    message_text = "📅 **Your Pending Scheduled Messages:**\n\n"
    
    for msg_id, scheduled_time, original_links, status in pending_messages:
        links = json.loads(original_links)
        dt = datetime.fromisoformat(scheduled_time)
        formatted_time = dt.strftime('%Y-%m-%d %H:%M UTC')
        
        message_text += f"**ID {msg_id}:**\n"
        message_text += f"🕐 {formatted_time}\n"
        message_text += f"🔗 {len(links)} link(s)\n"
        message_text += f"📊 Status: {status}\n\n"
    
    message_text += "Use `/cancel [id]` to cancel any scheduled message."
    
    await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel scheduled message"""
    if not context.args:
        await update.message.reply_text("Usage: `/cancel [message_id]`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        message_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid message ID!")
        return
    
    conn = sqlite3.connect(schedule_db)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE scheduled_messages 
        SET status = 'cancelled' 
        WHERE id = ? AND user_id = ? AND status = 'pending'
    ''', (message_id, update.effective_user.id))
    
    if cursor.rowcount > 0:
        conn.commit()
        await update.message.reply_text(f"✅ Scheduled message {message_id} cancelled!")
    else:
        await update.message.reply_text(f"❌ Message {message_id} not found or already processed!")
    
    conn.close()

# Keep existing instant processing function
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process messages for instant posting (existing function)"""
    message_text = update.message.text
    user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
    
    amazon_links = extract_all_amazon_links(message_text)
    
    if not amazon_links:
        return
    
    processing_msg = await update.message.reply_text(
        f"🔄 Processing {len(amazon_links)} Amazon link(s) for immediate posting..."
    )
    
    # Process and post immediately (same logic as before)
    results = []
    for original_url in amazon_links:
        try:
            if 'amzn.to' in original_url or 'a.co' in original_url:
                resolved_url = resolve_short_url(original_url)
            else:
                resolved_url = original_url
            
            asin = get_asin_from_url(resolved_url)
            affiliate_link = create_affiliate_link(resolved_url, asin)
            
            channel_message = f"""
🛒 **Amazon Product{' ' + asin if asin else ''}**

🔗 **Shop Now:** {affiliate_link}

📤 Shared by {user_mention}

#Amazon #Deals #Instant
            """
            
            if CHANNEL_ID:
                try:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=channel_message.strip(),
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=False
                    )
                    results.append(f"✅ Posted instantly: {affiliate_link}")
                except Exception as e:
                    results.append(f"❌ Failed to post: {str(e)}")
            else:
                results.append(f"🔗 Converted: {affiliate_link}")
                
        except Exception as e:
            results.append(f"❌ Error processing {original_url}: {str(e)}")
    
    result_text = "\n".join(results)
    await processing_msg.edit_text(f"**Instant Posting Results:**\n\n{result_text}", parse_mode=ParseMode.MARKDOWN)

def main():
    """Start the bot with scheduling capabilities"""
    if not TELEGRAM_TOKEN or not AFFILIATE_TAG:
        logging.error("Please set TELEGRAM_TOKEN and AFFILIATE_TAG environment variables")
        return
    
    # Initialize database
    init_database()
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    
    # Start the bot
    logging.info("Starting Amazon Affiliate Scheduler Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
