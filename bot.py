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
RULES=("📌 قوانین سوپرگروه تخصصی گویندگان\n\n"
"• هر مطلب فقط در موضوع مرتبط منتشر شود؛ ارسال تکراری در چند موضوع ممنوع است.\n"
"• احترام حرفه‌ای الزامی است؛ توهین، اسپم، لینک گروه‌های دیگر و محتوای نامرتبط ممنوع است.\n"
"• نمونه‌کار: حداکثر هفته‌ای ۱ پست و ماهی ۳ پست.\n"
"• معرفی گوینده: ماهی ۱ پست؛ برای اصلاح، پیام قبلی را ویرایش کنید.\n"
"• پروژه‌ها فقط پس از ارسال درخواست کامل به مدیران و تأیید آنان منتشر می‌شوند.\n"
"• تخلف‌ها: بار اول اخطار، بار دوم سکوت ۲۴ ساعته، بار سوم سکوت ۷ روزه، بار چهارم اخراج.\n\n"
"لطفاً پیش از فعالیت، قوانین کامل گروه را مطالعه کنید. مدیریت مسئولیت قراردادها و پرداخت‌ها را بر عهده ندارد.")
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
    outcome={1:'اخطار ثبت شد.',2:'به مدت ۲۴ ساعت سکوت می‌شوید.',3:'به مدت ۷ روز سکوت می‌شوید.',4:'از گروه اخراج و مسدود شدید.'}.get(count,'از گروه اخراج و مسدود شدید.')
    try:
        if count in (2,3):
            from datetime import timedelta
            until=now()+timedelta(hours=24) if count==2 else now()+timedelta(days=7)
            await bot.restrict_chat_member(GROUP_ID,uid,permissions={'can_send_messages':False},until_date=until)
        elif count>=4: await bot.ban_chat_member(GROUP_ID,uid)
    except Exception as e: log.warning('Could not apply restriction: %s',e)
    try: await bot.send_message(uid,f'⚠️ تخلف: {why}\nمرحله {min(count,4)} از ۴. {outcome}')
    except Exception: pass
    for admin in ADMINS:
        try: await bot.send_message(admin,f'⚠️ تخلف کاربر {uid} در گروه {GROUP_ID}: {why} (مرحله {count})')
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
    await m.answer('سلام! برای ارسال درخواست انتشار پروژه، متن کامل شامل نوع پروژه، توضیحات، حجم کار، سبک، زمان تحویل، شرایط همکاری و راه ارتباطی را همین‌جا بفرستید.\n\nقوانین گروه: /rules')
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
        await m.answer('لطفاً درخواست کامل (حداقل ۳۰ نویسه) را همراه با راه ارتباطی ارسال کنید.'); return
    rec=await db_call(lambda: DB.table('submissions').insert({'user_id':m.from_user.id,'username':m.from_user.username or '', 'content':text,'status':'pending','created_at':now().isoformat()}).execute())
    sid=rec.data[0]['id']
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ تأیید و انتشار',callback_data=f'approv:{sid}'),InlineKeyboardButton(text='❌ رد',callback_data=f'reject:{sid}')]])
    for admin in ADMINS:
        try: await bot.send_message(admin,f'درخواست پروژه جدید از {m.from_user.full_name} (@{m.from_user.username or "ندارد"}, ID {m.from_user.id}):\n\n{text}',reply_markup=kb)
        except Exception: pass
    await m.answer('درخواست شما برای بررسی به مدیران ارسال شد. پس از تأیید در موضوع پروژه‌ها منتشر می‌شود.')

@dp.callback_query(F.data.startswith(('approv:','reject:')))
async def review(c:CallbackQuery):
    if not c.from_user or not is_admin(c.from_user.id): await c.answer('دسترسی ندارید.',show_alert=True); return
    action,sid=c.data.split(':',1)
    result=await db_call(lambda: DB.table('submissions').select('*').eq('id',sid).eq('status','pending').limit(1).execute())
    if not result.data: await c.answer('این درخواست قبلاً بررسی شده است.',show_alert=True); return
    row=result.data[0]
    if action=='approv':
        thread=next((int(k) for k,v in TOPICS.items() if v=='projects'),None)
        if not thread: await c.answer('شناسه موضوع projects در TOPIC_MAP تعیین نشده.',show_alert=True); return
        await bot.send_message(GROUP_ID,'📢 درخواست همکاری تأییدشده\n\n'+row['content'],message_thread_id=thread)
        status='approved'
        try: await bot.send_message(int(row['user_id']),'درخواست شما تأیید و در گروه منتشر شد.')
        except Exception: pass
    else:
        status='rejected'
        try: await bot.send_message(int(row['user_id']),'درخواست شما توسط مدیران تأیید نشد.')
        except Exception: pass
    await db_call(lambda: DB.table('submissions').update({'status':status,'reviewed_by':c.from_user.id}).eq('id',sid).execute())
    await c.message.edit_reply_markup(reply_markup=None); await c.answer('انجام شد.')

@dp.message(F.chat.id==GROUP_ID)
async def moderate(m:Message):
    if not m.from_user or m.from_user.is_bot or is_admin(m.from_user.id): return
    topic=m.message_thread_id
    category=TOPICS.get(str(topic),'other')
    if category=='rules': await reject(m,'این موضوع فقط برای مالک گروه است.'); return
    if category=='projects':
        await reject(m,'انتشار پروژه فقط با تأیید مدیران ممکن است. برای ثبت درخواست، به ربات پیام خصوصی بدهید و اطلاعات کامل پروژه و راه ارتباطی را بفرستید.'); return
    text=msg_text(m)
    if any(w in text.casefold() for w in BAD_WORDS): await warn_and_enforce(m,'استفاده از واژه نامناسب'); return
    if re.search(r'(?:https?://)?t\.me/(?!GooyandeganPro(?:/|$))',text,re.I): await warn_and_enforce(m,'ارسال لینک گروه/کانال دیگر'); return
    uid=m.from_user.id
    if text:
        h=digest(text)
        dup=await db_call(lambda: DB.table('posts').select('id').eq('content_hash',h).neq('user_id',uid).limit(1).execute())
        # Also prevent same author's cross-topic repost; duplicate hash is checked regardless of user.
        dup_self=await db_call(lambda: DB.table('posts').select('id').eq('content_hash',h).limit(1).execute())
        if dup.data or dup_self.data: await warn_and_enforce(m,'انتشار محتوای تکراری در موضوعات مختلف'); return
    # Per-category quotas from the provided group rules.
    if category=='samples':
        w=await db_call(lambda:get_count(uid,category,week_start())); mo=await db_call(lambda:get_count(uid,category,month_start()))
        if w>=1 or mo>=3: await reject(m,'سقف نمونه‌کار: هفته‌ای ۱ پست و ماهی ۳ پست.'); return
    if category=='intro' and await db_call(lambda:get_count(uid,category,month_start()))>=1:
        await reject(m,'معرفی گوینده ماهی یک‌بار مجاز است؛ برای اصلاح، پیام قبلی را ویرایش کنید.'); return
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
            if len(q)>=10: await reject(m,'سقف گفت‌وگوی عمومی: ۱۰ پیام در ساعت، مگر پس از مشارکت ۵ عضو دیگر.'); return
            q.append((now().timestamp(),uid)); recent[('all',category)].append((now().timestamp(),uid))
        else:
            n=await db_call(lambda:get_count(uid,category,datetime.fromtimestamp(since,tz=timezone.utc).isoformat()))
            if n>=limits[category]: await reject(m,f'سقف این موضوع {limits[category]} پیام در ساعت است.'); return
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
