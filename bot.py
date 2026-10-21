"""Gooyandegan Telegram group moderator (aiogram 3 + Supabase).
Configure credentials and forum topic IDs via environment variables; see README.md.
"""
import asyncio, hashlib, json, logging, os, re, time
from collections import defaultdict, deque
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from supabase import create_client

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
log=logging.getLogger('gooyandegan')
TOKEN=os.environ['BOT_TOKEN']
SUPABASE_URL=os.environ['SUPABASE_URL']
SUPABASE_KEY=os.environ['SUPABASE_SERVICE_ROLE_KEY']
GROUP_ID=int(os.environ['GROUP_ID'])
ADMINS={int(x.strip()) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip()}
# Keys are Telegram forum thread IDs. These are the eight IDs supplied by the group owner.
# Map each ID to: general, samples, projects, intro, rules, tariffs, podcast, or other.
DEFAULT_TOPICS={"1":"general","213":"samples","14":"projects","71":"intro","3":"rules","66":"tariffs","72":"podcast","4":"other"}
TOPICS=json.loads(os.getenv('TOPIC_MAP',json.dumps(DEFAULT_TOPICS)))
RULES=("ðŸ“Œ Ù‚ÙˆØ§Ù†ÛŒÙ† Ø³ÙˆÙ¾Ø±Ú¯Ø±ÙˆÙ‡ ØªØ®ØµØµÛŒ Ú¯ÙˆÛŒÙ†Ø¯Ú¯Ø§Ù†\n\n"
"â€¢ Ù‡Ø± Ù…Ø·Ù„Ø¨ ÙÙ‚Ø· Ø¯Ø± Ù…ÙˆØ¶ÙˆØ¹ Ù…Ø±ØªØ¨Ø· Ù…Ù†ØªØ´Ø± Ø´ÙˆØ¯Ø› Ø§Ø±Ø³Ø§Ù„ ØªÚ©Ø±Ø§Ø±ÛŒ Ø¯Ø± Ú†Ù†Ø¯ Ù…ÙˆØ¶ÙˆØ¹ Ù…Ù…Ù†ÙˆØ¹ Ø§Ø³Øª.\n"
"â€¢ Ø§Ø­ØªØ±Ø§Ù… Ø­Ø±ÙÙ‡â€ŒØ§ÛŒ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³ØªØ› ØªÙˆÙ‡ÛŒÙ†ØŒ Ø§Ø³Ù¾Ù…ØŒ Ù„ÛŒÙ†Ú© Ú¯Ø±ÙˆÙ‡â€ŒÙ‡Ø§ÛŒ Ø¯ÛŒÚ¯Ø± Ùˆ Ù…Ø­ØªÙˆØ§ÛŒ Ù†Ø§Ù…Ø±ØªØ¨Ø· Ù…Ù…Ù†ÙˆØ¹ Ø§Ø³Øª.\n"
"â€¢ Ù†Ù…ÙˆÙ†Ù‡â€ŒÚ©Ø§Ø±: Ø­Ø¯Ø§Ú©Ø«Ø± Ù‡ÙØªÙ‡â€ŒØ§ÛŒ Û± Ù¾Ø³Øª Ùˆ Ù…Ø§Ù‡ÛŒ Û³ Ù¾Ø³Øª.\n"
"â€¢ Ù…Ø¹Ø±ÙÛŒ Ú¯ÙˆÛŒÙ†Ø¯Ù‡: Ù…Ø§Ù‡ÛŒ Û± Ù¾Ø³ØªØ› Ø¨Ø±Ø§ÛŒ Ø§ØµÙ„Ø§Ø­ØŒ Ù¾ÛŒØ§Ù… Ù‚Ø¨Ù„ÛŒ Ø±Ø§ ÙˆÛŒØ±Ø§ÛŒØ´ Ú©Ù†ÛŒØ¯.\n"
"â€¢ Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ ÙÙ‚Ø· Ù¾Ø³ Ø§Ø² Ø§Ø±Ø³Ø§Ù„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ú©Ø§Ù…Ù„ Ø¨Ù‡ Ù…Ø¯ÛŒØ±Ø§Ù† Ùˆ ØªØ£ÛŒÛŒØ¯ Ø¢Ù†Ø§Ù† Ù…Ù†ØªØ´Ø± Ù…ÛŒâ€ŒØ´ÙˆÙ†Ø¯.\n"
"â€¢ ØªØ®Ù„Ùâ€ŒÙ‡Ø§: Ø¨Ø§Ø± Ø§ÙˆÙ„ Ø§Ø®Ø·Ø§Ø±ØŒ Ø¨Ø§Ø± Ø¯ÙˆÙ… Ø³Ú©ÙˆØª Û²Û´ Ø³Ø§Ø¹ØªÙ‡ØŒ Ø¨Ø§Ø± Ø³ÙˆÙ… Ø³Ú©ÙˆØª Û· Ø±ÙˆØ²Ù‡ØŒ Ø¨Ø§Ø± Ú†Ù‡Ø§Ø±Ù… Ø§Ø®Ø±Ø§Ø¬.\n\n"
"Ù„Ø·ÙØ§Ù‹ Ù¾ÛŒØ´ Ø§Ø² ÙØ¹Ø§Ù„ÛŒØªØŒ Ù‚ÙˆØ§Ù†ÛŒÙ† Ú©Ø§Ù…Ù„ Ú¯Ø±ÙˆÙ‡ Ø±Ø§ Ù…Ø·Ø§Ù„Ø¹Ù‡ Ú©Ù†ÛŒØ¯. Ù…Ø¯ÛŒØ±ÛŒØª Ù…Ø³Ø¦ÙˆÙ„ÛŒØª Ù‚Ø±Ø§Ø±Ø¯Ø§Ø¯Ù‡Ø§ Ùˆ Ù¾Ø±Ø¯Ø§Ø®Øªâ€ŒÙ‡Ø§ Ø±Ø§ Ø¨Ø± Ø¹Ù‡Ø¯Ù‡ Ù†Ø¯Ø§Ø±Ø¯.")
# Expand this list via FORBIDDEN_WORDS (comma-separated) to match community policy.
BAD_WORDS=[x.strip().casefold() for x in os.getenv('FORBIDDEN_WORDS','').split(',') if x.strip()]
DB=create_client(SUPABASE_URL,SUPABASE_KEY)
bot=Bot(TOKEN)
dp=Dispatcher()
# general topic allows 10 posts/hour unless at least 5 other users posted since author's previous post.
recent=defaultdict(lambda: deque(maxlen=500))

def now(): return datetime.now(timezone.utc)
def month_start(): return now().replace(day=1,hour=0,minute=0,second=0,microsecond=0).isoformat()
def week_start():
    n=now(); return n.replace(hour=0,minute=0,second=0,microsecond=0).isoformat() if n.weekday()==0 else (n.replace(hour=0,minute=0,second=0,microsecond=0)-__import__('datetime').timedelta(days=n.weekday())).isoformat()
def msg_text(m):
    if m.text: return m.text.strip()
    if m.caption: return m.caption.strip()
    if m.photo: return 'photo:'+m.photo[-1].file_unique_id
    if m.document: return 'document:'+m.document.file_unique_id
    if m.voice: return 'voice:'+m.voice.file_unique_id
    if m.video: return 'video:'+m.video.file_unique_id
    if m.audio: return 'audio:'+m.audio.file_unique_id
    if m.sticker: return 'sticker:'+m.sticker.file_unique_id
    return ''
def digest(s): return hashlib.sha256(re.sub(r'\s+',' ',s.casefold()).strip().encode()).hexdigest()
def is_admin(uid): return uid in ADMINS
async def db_call(fn): return await asyncio.to_thread(fn)
def get_count(uid,cat,since):
    res=DB.table('posts').select('id').eq('user_id',uid).eq('category',cat).gte('created_at',since).execute()
    return len(res.data or [])
def violation_count(uid):
    res=DB.table('moderation').select('strikes').eq('user_id',uid).eq('chat_id',GROUP_ID).limit(1).execute()
    return int(res.data[0]['strikes']) if res.data else 0
def update_strikes(uid, strikes):
    DB.table('moderation').upsert({'user_id':uid,'chat_id':GROUP_ID,'strikes':strikes,'updated_at':now().isoformat()},on_conflict='user_id,chat_id').execute()
async def warn_and_enforce(m:Message, why:str):
    uid=m.from_user.id
    try: await m.delete()
    except Exception: pass
    count=await db_call(lambda: violation_count(uid))+1
    await db_call(lambda: update_strikes(uid,count))
    outcome={1:'Ø§Ø®Ø·Ø§Ø± Ø«Ø¨Øª Ø´Ø¯.',2:'Ø¨Ù‡ Ù…Ø¯Øª Û²Û´ Ø³Ø§Ø¹Øª Ø³Ú©ÙˆØª Ù…ÛŒâ€ŒØ´ÙˆÛŒØ¯.',3:'Ø¨Ù‡ Ù…Ø¯Øª Û· Ø±ÙˆØ² Ø³Ú©ÙˆØª Ù…ÛŒâ€ŒØ´ÙˆÛŒØ¯.',4:'Ø§Ø² Ú¯Ø±ÙˆÙ‡ Ø§Ø®Ø±Ø§Ø¬ Ùˆ Ù…Ø³Ø¯ÙˆØ¯ Ø´Ø¯ÛŒØ¯.'}.get(count,'Ø§Ø² Ú¯Ø±ÙˆÙ‡ Ø§Ø®Ø±Ø§Ø¬ Ùˆ Ù…Ø³Ø¯ÙˆØ¯ Ø´Ø¯ÛŒØ¯.')
    try:
        if count in (2,3):
            from datetime import timedelta
            until=now()+timedelta(hours=24) if count==2 else now()+timedelta(days=7)
            await bot.restrict_chat_member(GROUP_ID,uid,permissions={'can_send_messages':False},until_date=until)
        elif count>=4: await bot.ban_chat_member(GROUP_ID,uid)
    except Exception as e: log.warning('Could not apply restriction: %s',e)
    try: await bot.send_message(uid,f'âš ï¸ ØªØ®Ù„Ù: {why}\nÙ…Ø±Ø­Ù„Ù‡ {min(count,4)} Ø§Ø² Û´. {outcome}')
    except Exception: pass
    for admin in ADMINS:
        try: await bot.send_message(admin,f'âš ï¸ ØªØ®Ù„Ù Ú©Ø§Ø±Ø¨Ø± {uid} Ø¯Ø± Ú¯Ø±ÙˆÙ‡ {GROUP_ID}: {why} (Ù…Ø±Ø­Ù„Ù‡ {count})')
        except Exception: pass
async def reject(m,reason):
    try: await m.delete()
    except Exception: pass
    try: await bot.send_message(m.from_user.id,reason)
    except Exception: pass

def media_id(m):
    if m.photo: return ('photo',m.photo[-1].file_id)
    if m.video: return ('video',m.video.file_id)
    if m.document: return ('document',m.document.file_id)
    if m.voice: return ('voice',m.voice.file_id)
    if m.audio: return ('audio',m.audio.file_id)
    return None

@dp.message(CommandStart(),F.chat.type==ChatType.PRIVATE)
async def start(m:Message):
    await m.answer('Ø³Ù„Ø§Ù…! Ø¨Ø±Ø§ÛŒ Ø§Ø±Ø³Ø§Ù„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø§Ù†ØªØ´Ø§Ø± Ù¾Ø±ÙˆÚ˜Ù‡ØŒ Ù…ØªÙ† Ú©Ø§Ù…Ù„ Ø´Ø§Ù…Ù„ Ù†ÙˆØ¹ Ù¾Ø±ÙˆÚ˜Ù‡ØŒ ØªÙˆØ¶ÛŒØ­Ø§ØªØŒ Ø­Ø¬Ù… Ú©Ø§Ø±ØŒ Ø³Ø¨Ú©ØŒ Ø²Ù…Ø§Ù† ØªØ­ÙˆÛŒÙ„ØŒ Ø´Ø±Ø§ÛŒØ· Ù‡Ù…Ú©Ø§Ø±ÛŒ Ùˆ Ø±Ø§Ù‡ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ Ø±Ø§ Ù‡Ù…ÛŒÙ†â€ŒØ¬Ø§ Ø¨ÙØ±Ø³ØªÛŒØ¯.\n\nÙ‚ÙˆØ§Ù†ÛŒÙ† Ú¯Ø±ÙˆÙ‡: /rules')
@dp.message(Command('rules'))
async def rules(m:Message): await m.answer(RULES)
@dp.message(F.new_chat_members)
async def welcome(m:Message):
    for u in m.new_chat_members:
        if u.is_bot: continue
        try: await bot.send_message(u.id,RULES)
        except Exception: pass

@dp.message(F.chat.type==ChatType.PRIVATE,~F.text.startswith('/'))
async def project_dm(m:Message):
    # A private request is sent to admins for approval; actual publication is text-only for safety.
    text=msg_text(m)
    if not text or len(text)<30:
        await m.answer('Ù„Ø·ÙØ§Ù‹ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ú©Ø§Ù…Ù„ (Ø­Ø¯Ø§Ù‚Ù„ Û³Û° Ù†ÙˆÛŒØ³Ù‡) Ø±Ø§ Ù‡Ù…Ø±Ø§Ù‡ Ø¨Ø§ Ø±Ø§Ù‡ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ Ø§Ø±Ø³Ø§Ù„ Ú©Ù†ÛŒØ¯.'); return
    rec=await db_call(lambda: DB.table('submissions').insert({'user_id':m.from_user.id,'username':m.from_user.username or '', 'content':text,'status':'pending','created_at':now().isoformat()}).execute())
    sid=rec.data[0]['id']
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='âœ… ØªØ£ÛŒÛŒØ¯ Ùˆ Ø§Ù†ØªØ´Ø§Ø±',callback_data=f'approv:{sid}'),InlineKeyboardButton(text='âŒ Ø±Ø¯',callback_data=f'reject:{sid}')]])
    for admin in ADMINS:
        try: await bot.send_message(admin,f'Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ù¾Ø±ÙˆÚ˜Ù‡ Ø¬Ø¯ÛŒØ¯ Ø§Ø² {m.from_user.full_name} (@{m.from_user.username or "Ù†Ø¯Ø§Ø±Ø¯"}, ID {m.from_user.id}):\n\n{text}',reply_markup=kb)
        except Exception: pass
    await m.answer('Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø´Ù…Ø§ Ø¨Ø±Ø§ÛŒ Ø¨Ø±Ø±Ø³ÛŒ Ø¨Ù‡ Ù…Ø¯ÛŒØ±Ø§Ù† Ø§Ø±Ø³Ø§Ù„ Ø´Ø¯. Ù¾Ø³ Ø§Ø² ØªØ£ÛŒÛŒØ¯ Ø¯Ø± Ù…ÙˆØ¶ÙˆØ¹ Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ Ù…Ù†ØªØ´Ø± Ù…ÛŒâ€ŒØ´ÙˆØ¯.')

@dp.callback_query(F.data.startswith(('approv:','reject:')))
async def review(c:CallbackQuery):
    if not c.from_user or not is_admin(c.from_user.id): await c.answer('Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯.',show_alert=True); return
    action,sid=c.data.split(':',1)
    result=await db_call(lambda: DB.table('submissions').select('*').eq('id',sid).eq('status','pending').limit(1).execute())
    if not result.data: await c.answer('Ø§ÛŒÙ† Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ù‚Ø¨Ù„Ø§Ù‹ Ø¨Ø±Ø±Ø³ÛŒ Ø´Ø¯Ù‡ Ø§Ø³Øª.',show_alert=True); return
    row=result.data[0]
    if action=='approv':
        thread=next((int(k) for k,v in TOPICS.items() if v=='projects'),None)
        if not thread: await c.answer('Ø´Ù†Ø§Ø³Ù‡ Ù…ÙˆØ¶ÙˆØ¹ projects Ø¯Ø± TOPIC_MAP ØªØ¹ÛŒÛŒÙ† Ù†Ø´Ø¯Ù‡.',show_alert=True); return
        await bot.send_message(GROUP_ID,'ðŸ“¢ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ù‡Ù…Ú©Ø§Ø±ÛŒ ØªØ£ÛŒÛŒØ¯Ø´Ø¯Ù‡\n\n'+row['content'],message_thread_id=thread)
        status='approved'
        try: await bot.send_message(int(row['user_id']),'Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø´Ù…Ø§ ØªØ£ÛŒÛŒØ¯ Ùˆ Ø¯Ø± Ú¯Ø±ÙˆÙ‡ Ù…Ù†ØªØ´Ø± Ø´Ø¯.')
        except Exception: pass
    else:
        status='rejected'
        try: await bot.send_message(int(row['user_id']),'Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø´Ù…Ø§ ØªÙˆØ³Ø· Ù…Ø¯ÛŒØ±Ø§Ù† ØªØ£ÛŒÛŒØ¯ Ù†Ø´Ø¯.')
        except Exception: pass
    await db_call(lambda: DB.table('submissions').update({'status':status,'reviewed_by':c.from_user.id}).eq('id',sid).execute())
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯.')

@dp.message(F.chat.id==GROUP_ID)
async def moderate(m:Message):
    if not m.from_user or m.from_user.is_bot or is_admin(m.from_user.id): return
    topic=m.message_thread_id
    category=TOPICS.get(str(topic),'other')
    if category=='rules': await reject(m,'Ø§ÛŒÙ† Ù…ÙˆØ¶ÙˆØ¹ ÙÙ‚Ø· Ø¨Ø±Ø§ÛŒ Ù…Ø§Ù„Ú© Ú¯Ø±ÙˆÙ‡ Ø§Ø³Øª.'); return
    if category=='projects':
        await reject(m,'Ø§Ù†ØªØ´Ø§Ø± Ù¾Ø±ÙˆÚ˜Ù‡ ÙÙ‚Ø· Ø¨Ø§ ØªØ£ÛŒÛŒØ¯ Ù…Ø¯ÛŒØ±Ø§Ù† Ù…Ù…Ú©Ù† Ø§Ø³Øª. Ø¨Ø±Ø§ÛŒ Ø«Ø¨Øª Ø¯Ø±Ø®ÙˆØ§Ø³ØªØŒ Ø¨Ù‡ Ø±Ø¨Ø§Øª Ù¾ÛŒØ§Ù… Ø®ØµÙˆØµÛŒ Ø¨Ø¯Ù‡ÛŒØ¯ Ùˆ Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ú©Ø§Ù…Ù„ Ù¾Ø±ÙˆÚ˜Ù‡ Ùˆ Ø±Ø§Ù‡ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ Ø±Ø§ Ø¨ÙØ±Ø³ØªÛŒØ¯.'); return
    text=msg_text(m)
    if any(w in text.casefold() for w in BAD_WORDS): await warn_and_enforce(m,'Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø§Ø² ÙˆØ§Ú˜Ù‡ Ù†Ø§Ù…Ù†Ø§Ø³Ø¨'); return
    if re.search(r'(?:https?://)?t\.me/(?!GooyandeganPro(?:/|$))',text,re.I): await warn_and_enforce(m,'Ø§Ø±Ø³Ø§Ù„ Ù„ÛŒÙ†Ú© Ú¯Ø±ÙˆÙ‡/Ú©Ø§Ù†Ø§Ù„ Ø¯ÛŒÚ¯Ø±'); return
    uid=m.from_user.id
    if text:
        h=digest(text)
        dup=await db_call(lambda: DB.table('posts').select('id').eq('content_hash',h).neq('user_id',uid).limit(1).execute())
        # Also prevent same author's cross-topic repost; duplicate hash is checked regardless of user.
        dup_self=await db_call(lambda: DB.table('posts').select('id').eq('content_hash',h).limit(1).execute())
        if dup.data or dup_self.data: await warn_and_enforce(m,'Ø§Ù†ØªØ´Ø§Ø± Ù…Ø­ØªÙˆØ§ÛŒ ØªÚ©Ø±Ø§Ø±ÛŒ Ø¯Ø± Ù…ÙˆØ¶ÙˆØ¹Ø§Øª Ù…Ø®ØªÙ„Ù'); return
    # Per-category quotas from the provided group rules.
    if category=='samples':
        w=await db_call(lambda:get_count(uid,category,week_start())); mo=await db_call(lambda:get_count(uid,category,month_start()))
        if w>=1 or mo>=3: await reject(m,'Ø³Ù‚Ù Ù†Ù…ÙˆÙ†Ù‡â€ŒÚ©Ø§Ø±: Ù‡ÙØªÙ‡â€ŒØ§ÛŒ Û± Ù¾Ø³Øª Ùˆ Ù…Ø§Ù‡ÛŒ Û³ Ù¾Ø³Øª.'); return
    if category=='intro' and await db_call(lambda:get_count(uid,category,month_start()))>=1:
        await reject(m,'Ù…Ø¹Ø±ÙÛŒ Ú¯ÙˆÛŒÙ†Ø¯Ù‡ Ù…Ø§Ù‡ÛŒ ÛŒÚ©â€ŒØ¨Ø§Ø± Ù…Ø¬Ø§Ø² Ø§Ø³ØªØ› Ø¨Ø±Ø§ÛŒ Ø§ØµÙ„Ø§Ø­ØŒ Ù¾ÛŒØ§Ù… Ù‚Ø¨Ù„ÛŒ Ø±Ø§ ÙˆÛŒØ±Ø§ÛŒØ´ Ú©Ù†ÛŒØ¯.'); return
    limits={'tariffs':15,'podcast':10,'general':10}
    if category in limits:
        since=(now().timestamp()-3600)
        if category=='general':
            q=recent[(uid,category)]
            while q and q[0][0]<since: q.popleft()
            # Replenish user's quota after five distinct other members have spoken since their oldest recent post.
            if q:
                others={u for ts,u in recent[('all',category)] if ts>q[0][0] and u!=uid}
                if len(others)>=5: q.clear()
            if len(q)>=10: await reject(m,'Ø³Ù‚Ù Ú¯ÙØªâ€ŒÙˆÚ¯ÙˆÛŒ Ø¹Ù…ÙˆÙ…ÛŒ: Û±Û° Ù¾ÛŒØ§Ù… Ø¯Ø± Ø³Ø§Ø¹ØªØŒ Ù…Ú¯Ø± Ù¾Ø³ Ø§Ø² Ù…Ø´Ø§Ø±Ú©Øª Ûµ Ø¹Ø¶Ùˆ Ø¯ÛŒÚ¯Ø±.'); return
            q.append((now().timestamp(),uid)); recent[('all',category)].append((now().timestamp(),uid))
        else:
            n=await db_call(lambda:get_count(uid,category,datetime.fromtimestamp(since,tz=timezone.utc).isoformat()))
            if n>=limits[category]: await reject(m,f'Ø³Ù‚Ù Ø§ÛŒÙ† Ù…ÙˆØ¶ÙˆØ¹ {limits[category]} Ù¾ÛŒØ§Ù… Ø¯Ø± Ø³Ø§Ø¹Øª Ø§Ø³Øª.'); return
    # persist after all checks; hash/media enables basic duplicate detection
    ident=text or (msg_text(m))
    if ident:
        await db_call(lambda: DB.table('posts').insert({'user_id':uid,'chat_id':GROUP_ID,'thread_id':topic or 0,'category':category,'content_hash':digest(ident),'created_at':now().isoformat()}).execute())

# --- Render Free Web Service keep-alive web server (aiohttp, same process/loop) ---
from aiohttp import web

async def handle_root(request: web.Request) -> web.Response:
    return web.Response(text='Gooyandegan bot is running', status=200)

async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text='ok', status=200)

def build_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/health', handle_health)
    return app

async def main():
    if not ADMINS: raise RuntimeError('Set ADMIN_IDS to comma-separated Telegram user IDs.')
    runner = web.AppRunner(build_web_app())
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=int(os.getenv('PORT', '10000')))
    await site.start()
    log.info('Health web server listening on 0.0.0.0:%s', os.getenv('PORT', '10000'))
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
if __name__=='__main__': asyncio.run(main())
