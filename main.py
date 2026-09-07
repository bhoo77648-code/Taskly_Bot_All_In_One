import asyncio
import json
import re
import secrets
from decimal import Decimal, InvalidOperation

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import *
from database import *


dp = Dispatcher()

TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a9df523b3ef'
HEX40 = re.compile(r'^0x[a-fA-F0-9]{40}$')
TX_RE = re.compile(r'^0x[a-fA-F0-9]{64}$')


class TaskState(StatesGroup):
    network = State(); title = State(); url = State(); reward = State(); limit = State()


class ProofState(StatesGroup):
    first = State(); second = State()


class ChannelState(StatesGroup):
    network = State(); title = State(); url = State(); edit_url = State()


class OrderState(StatesGroup):
    network = State(); target = State(); quantity = State(); txid = State()


class WithdrawState(StatesGroup):
    amount = State(); wallet = State(); txid = State(); receipt = State()


class PriceState(StatesGroup):
    network = State(); price = State()


class BalanceState(StatesGroup):
    user = State(); amount = State()


def is_admin(uid):
    return uid == ADMIN_ID


TEXT = {
    'fa': {
        'balance': '💰 موجودی', 'tasks': '🔥 تسک‌ها', 'withdraw': '💸 برداشت',
        'profile': '👤 پروفایل', 'referral': '👥 رفرال', 'rank': '🏆 رتبه‌بندی', 'language': '🌐 زبان',
        'promo': '🛒 خرید سابسکرایبر', 'admin': '👑 مدیریت',
        'welcome': 'به Taskly Bot خوش آمدید.'
    },
    'en': {
        'balance': '💰 Balance', 'tasks': '🔥 Tasks', 'withdraw': '💸 Withdraw',
        'profile': '👤 Profile', 'referral': '👥 Referral', 'rank': '🏆 Ranking', 'language': '🌐 Language',
        'promo': '🛒 Buy Subscribers', 'admin': '👑 Admin',
        'welcome': 'Welcome to Taskly Bot.'
    },
    'hi': {
        'balance': '💰 बैलेंस', 'tasks': '🔥 टास्क', 'withdraw': '💸 निकासी',
        'profile': '👤 प्रोफ़ाइल', 'referral': '👥 रेफरल', 'rank': '🏆 रैंकिंग', 'language': '🌐 भाषा',
        'promo': '🛒 सब्सक्राइबर खरीदें', 'admin': '👑 एडमिन',
        'welcome': 'Taskly Bot में आपका स्वागत है।'
    }
}


UI = {
 'fa': {
  'lang_prompt':'🌐 زبان را انتخاب کنید:', 'blocked':'⛔ حساب شما توسط مدیر مسدود شده است.',
  'welcome':'به Taskly Bot خوش آمدید.', 'balance':'💰 موجودی: ${:.4f} USDT',
  'tasks_empty':'فعلاً تسک جدیدی برای شما موجود نیست.', 'use_menu':'از منو استفاده کن 👇',
  'withdraw':'💸 برداشت','withdraw_method':'روش برداشت را انتخاب کن:','usdt':'💵 USDT BEP20',
  'min_withdraw':'حداقل برداشت: ${:.2f}','profile':'👤 پروفایل','referral':'👥 رفرال',
  'referral_commission':'💵 کمیسیون رفرال: ۱۰٪ از پاداش تسک کاربر دعوت‌شده',
  'rank':'🏆 رتبه‌بندی ۲۴ ساعت اخیر','promo':'🛒 خرید سابسکرایبر',
  'promo_intro':'شبکه موردنظر را انتخاب کن. قیمت هر شبکه همین‌جا مشخص است:',
  'promo_payment':'پرداخت خرید با USDT BEP20 مستقیم به آدرس پرداخت سیستم انجام می‌شود و وارد موجودی نمی‌شود.',
  'choose':'انتخاب کن','network':'شبکه','price':'قیمت','target':'🔗 لینک کانال/پروفایل مقصد را بفرست.',
  'quantity':'تعداد سابسکرایبر را انتخاب کن:','custom_qty':'✏️ تعداد دلخواه','cancel':'❌ لغو',
  'invalid_link':'❌ لینک نامعتبر است. لینک باید با https:// یا http:// شروع شود.',
  'invalid_amount':'❌ مقدار صحیح وارد کن. مثال: 2','checking':'🔎 در حال بررسی موجودی شما...',
  'insufficient':'❌ موجودی کافی نیست. موجودی شما: ${:.4f} USDT\n💸 درخواست شما: ${:.4f} USDT',
  'address_ok':'✅ آدرس دریافت شد.','send_amount':'حالا مقدار برداشت را به دلار بفرست.\nمثال: 2',
  'wallet_prompt':'آدرس کیف پول BEP20 خودت را بفرست.\nمثال: 0x...',
  'wallet_bad':'❌ آدرس صحیح نیست. آدرس BEP20 باید با 0x شروع شود و 40 کاراکتر هگز داشته باشد.',
  'order_target':'بعد از انتخاب شبکه، لینک کانال/پروفایل مقصد را وارد کن.',
 },
 'en': {
  'lang_prompt':'🌐 Choose your language:', 'blocked':'⛔ Your account has been blocked by the admin.',
  'welcome':'Welcome to Taskly Bot.', 'balance':'💰 Balance: ${:.4f} USDT',
  'tasks_empty':'There are no new tasks available for you right now.', 'use_menu':'Please use the menu 👇',
  'withdraw':'💸 Withdraw','withdraw_method':'Choose Withdraw Method:','usdt':'💵 USDT BEP20',
  'min_withdraw':'Minimum withdrawal: ${:.2f}','profile':'👤 Profile','referral':'👥 Referral',
  'referral_commission':'💵 Referral commission: 10% of the invited user’s task reward',
  'rank':'🏆 Ranking — last 24 hours','promo':'🛒 Buy Subscribers',
  'promo_intro':'Choose a network. The price for each network is shown below:',
  'promo_payment':'Payment for purchases is sent in USDT BEP20 directly to the system payment address and is not added to your balance.',
  'choose':'Choose','network':'Network','price':'Price','target':'🔗 Send the target channel/profile link.',
  'quantity':'Choose the subscriber quantity:','custom_qty':'✏️ Custom quantity','cancel':'❌ Cancel',
  'invalid_link':'❌ Invalid link. It must start with https:// or http://.',
  'invalid_amount':'❌ Enter a valid amount. Example: 2','checking':'🔎 Checking your balance...',
  'insufficient':'❌ Insufficient balance. Your balance: ${:.4f} USDT\n💸 Requested: ${:.4f} USDT',
  'address_ok':'✅ Wallet address received.','send_amount':'Now enter the withdrawal amount.\nExample: 2',
  'wallet_prompt':'Send your BEP20 wallet address.\nExample: 0x...',
  'wallet_bad':'❌ Invalid address. A BEP20 address must start with 0x and contain 40 hexadecimal characters.',
  'order_target':'After choosing a network, send the target channel/profile link.',
 },
 'hi': {
  'lang_prompt':'🌐 अपनी भाषा चुनें:', 'blocked':'⛔ आपका खाता एडमिन द्वारा ब्लॉक किया गया है।',
  'welcome':'Taskly Bot में आपका स्वागत है।', 'balance':'💰 बैलेंस: ${:.4f} USDT',
  'tasks_empty':'अभी आपके लिए कोई नया टास्क उपलब्ध नहीं है।', 'use_menu':'कृपया मेनू का उपयोग करें 👇',
  'withdraw':'💸 निकासी','withdraw_method':'निकासी का तरीका चुनें:','usdt':'💵 USDT BEP20',
  'min_withdraw':'न्यूनतम निकासी: ${:.2f}','profile':'👤 प्रोफ़ाइल','referral':'👥 रेफरल',
  'referral_commission':'💵 रेफरल कमीशन: आमंत्रित उपयोगकर्ता के टास्क रिवॉर्ड का 10%',
  'rank':'🏆 रैंकिंग — पिछले 24 घंटे','promo':'🛒 सब्सक्राइबर खरीदें',
  'promo_intro':'नेटवर्क चुनें। हर नेटवर्क की कीमत नीचे दिखाई गई है:',
  'promo_payment':'खरीद का भुगतान USDT BEP20 में सीधे सिस्टम के भुगतान पते पर जाता है और आपके बैलेंस में नहीं जुड़ता।',
  'choose':'चुनें','network':'नेटवर्क','price':'कीमत','target':'🔗 टारगेट चैनल/प्रोफ़ाइल का लिंक भेजें।',
  'quantity':'सब्सक्राइबर की संख्या चुनें:','custom_qty':'✏️ कस्टम संख्या','cancel':'❌ रद्द करें',
  'invalid_link':'❌ लिंक गलत है। यह https:// या http:// से शुरू होना चाहिए।',
  'invalid_amount':'❌ सही राशि दर्ज करें। उदाहरण: 2','checking':'🔎 आपका बैलेंस जांचा जा रहा है...',
  'insufficient':'❌ बैलेंस पर्याप्त नहीं है। आपका बैलेंस: ${:.4f} USDT\n💸 अनुरोधित: ${:.4f} USDT',
  'address_ok':'✅ वॉलेट पता मिल गया।','send_amount':'अब निकासी की राशि दर्ज करें।\nउदाहरण: 2',
  'wallet_prompt':'अपना BEP20 वॉलेट पता भेजें।\nउदाहरण: 0x...',
  'wallet_bad':'❌ पता गलत है। BEP20 पता 0x से शुरू होना चाहिए और 40 hexadecimal characters होना चाहिए।',
  'order_target':'नेटवर्क चुनने के बाद टारगेट चैनल/प्रोफ़ाइल का लिंक भेजें।',
 }
}

def tr(lang, key, *args):
    text = UI.get(lang, UI['fa']).get(key, UI['fa'].get(key, key))
    return text.format(*args) if args else text

async def user_lang(uid):
    u=await get_user(uid)
    return u[2] if u and u[2] in UI else 'fa'


def user_menu(lang, admin=False):
    t = TEXT.get(lang, TEXT['fa'])
    kb = ReplyKeyboardBuilder()
    for x in [t['balance'], t['tasks'], t['withdraw'], t['profile'], t['referral'], t['rank'], t['language'], t['promo']]:
        kb.button(text=x)
    if admin:
        kb.button(text=t['admin'])
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def network_keyboard(prefix):
    kb = InlineKeyboardBuilder()
    for n in NETWORKS:
        kb.button(text=n, callback_data=f'{prefix}:{n}')
    kb.adjust(2)
    return kb.as_markup()


def language_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text='🇮🇷 فارسی', callback_data='lang:fa')
    kb.button(text='🇬🇧 English', callback_data='lang:en')
    kb.button(text='🇮🇳 हिन्दी', callback_data='lang:hi')
    kb.adjust(1)
    return kb.as_markup()


def cancel_keyboard():
    kb = InlineKeyboardBuilder(); kb.button(text='❌ لغو', callback_data='cancel')
    return kb.as_markup()


def admin_keyboard():
    kb = InlineKeyboardBuilder()
    items = [
        ('📊 داشبورد', 'admin:dash'), ('➕ افزودن تسک', 'admin:addtask'),
        ('📋 تسک‌ها', 'admin:tasks'), ('🧾 بررسی مدارک', 'admin:proofs'),
        ('📢 مدیریت کانال‌ها', 'admin:channels'), ('👥 مدیریت کاربران', 'admin:users'),
        ('🛒 سفارش‌ها', 'admin:orders'), ('💸 برداشت‌ها', 'admin:withdrawals'),
        ('💵 قیمت سابسکرایبر', 'admin:prices')
    ]
    for label, data in items:
        kb.button(text=label, callback_data=data)
    kb.adjust(2)
    return kb.as_markup()


async def ensure_user(message: Message):
    uid = message.from_user.id
    u = await get_user(uid)
    if not u:
        raw = (message.text or '').split(maxsplit=1)
        ref = raw[1] if len(raw) > 1 else ''
        inviter = await get_user_by_referral_code(ref[4:]) if ref.startswith('ref_') else None
        inviter_id = inviter[0] if inviter and inviter[0] != uid else None
        await create_user(uid, message.from_user.username, secrets.token_hex(4).upper(), inviter_id)
        if inviter_id:
            await create_referral(inviter_id, uid, float(await get_setting('referral_rate', REFERRAL_RATE)))
    else:
        await update_username(uid, message.from_user.username)
    return await get_user(uid)


async def is_blocked(uid):
    u = await get_user(uid)
    return bool(u and u[6])


async def broadcast(bot: Bot, text: str, reply_markup=None):
    sent = 0
    for uid in await all_user_ids():
        try:
            await bot.send_message(uid, text, reply_markup=reply_markup)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.04)
    return sent


async def broadcast_new_task(bot, task):
    kb = InlineKeyboardBuilder(); kb.button(text='🔥 مشاهده و انجام تسک', callback_data=f'task:open:{task[0]}')
    text = (
        f'🔔 اطلاعیه: یک تسک جدید آمد!\n\n🌐 {task[2]}\n'
        f'📝 {task[3]}\n💰 پاداش: ${task[5]:.4f}\n👥 ظرفیت: {task[6]}\n\n'
        'برای انجام تسک روی دکمه زیر بزن.'
    )
    return await broadcast(bot, text, kb.as_markup())


async def bsc_rpc(method, params):
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(BSC_RPC_URL, json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(f'RPC HTTP {resp.status}')
            data = await resp.json()
            if data.get('error'):
                raise RuntimeError(str(data['error']))
            return data.get('result')


async def verify_bep20_usdt_payment(txid: str, expected_amount: float):
    if not TX_RE.fullmatch(txid):
        return False, 'TXID format is invalid.'
    try:
        receipt = await bsc_rpc('eth_getTransactionReceipt', [txid])
        if not receipt:
            return False, 'Transaction not found yet.'
        if receipt.get('status') != '0x1':
            return False, 'Transaction failed on-chain.'
        block_hex = receipt.get('blockNumber')
        latest_hex = await bsc_rpc('eth_blockNumber', [])
        if not block_hex or not latest_hex:
            return False, 'Could not read confirmations.'
        confirmations = int(latest_hex, 16) - int(block_hex, 16) + 1
        if confirmations < PAYMENT_CONFIRMATIONS:
            return False, f'Waiting for confirmations: {confirmations}/{PAYMENT_CONFIRMATIONS}.'

        wanted_token = USDT_CONTRACT.lower()
        wanted_to = PAYMENT_WALLET_ADDRESS.lower().replace('0x', '')
        wanted_units = int((Decimal(str(expected_amount)) * (Decimal(10) ** USDT_DECIMALS)).to_integral_value())

        for log in receipt.get('logs', []):
            if str(log.get('address', '')).lower() != wanted_token:
                continue
            topics = log.get('topics') or []
            if len(topics) < 3 or topics[0].lower() != TRANSFER_TOPIC:
                continue
            to_addr = topics[2][-40:].lower()
            amount_units = int(log.get('data', '0x0'), 16)
            if to_addr == wanted_to and amount_units == wanted_units:
                return True, f'Payment verified. Confirmations: {confirmations}.'
        return False, 'No exact USDT BEP20 transfer to the configured wallet was found in this transaction.'
    except Exception as exc:
        return False, f'Automatic verification is temporarily unavailable: {exc}'


# ---------------- START / LANGUAGE ----------------
@dp.message(CommandStart())
async def start(message: Message):
    u = await ensure_user(message)
    if u[6] and not is_admin(message.from_user.id):
        return await message.answer(tr(u[2], 'blocked'))
    if u[2] in UI and u[2] != 'fa':
        return await message.answer(tr(u[2], 'welcome'), reply_markup=user_menu(u[2], is_admin(message.from_user.id)))
    await message.answer(tr('fa', 'lang_prompt'), reply_markup=language_keyboard())


@dp.callback_query(F.data.startswith('lang:'))
async def language(call: CallbackQuery):
    lang = call.data.split(':')[1]
    await set_language(call.from_user.id, lang)
    await call.message.answer(tr(lang, 'welcome'), reply_markup=user_menu(lang, is_admin(call.from_user.id)))
    await call.answer()


# ---------------- TASKS ----------------
@dp.callback_query(F.data.startswith('task:open:'))
async def task_open(call: CallbackQuery):
    if await is_blocked(call.from_user.id):
        return await call.answer('حساب مسدود است.', show_alert=True)
    tid = int(call.data.split(':')[-1])
    task = await get_task(tid)
    if not task or task[7] != 'active':
        return await call.answer('تسک فعال نیست.', show_alert=True)
    if await user_has_completion(tid, call.from_user.id):
        return await call.answer('این تسک قبلاً برای شما نمایش/ثبت شده است.', show_alert=True)
    count = await approved_count(tid)
    if count >= task[6]:
        return await call.answer('ظرفیت تکمیل شده.', show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text='🔗 باز کردن کانال/لینک', url=task[4])
    kb.button(text='📸 ارسال دو اسکرین‌شات', callback_data=f'proof:start:{tid}')
    kb.adjust(1)
    await call.message.answer(
        f'🔥 {task[3]}\n🌐 {task[2]}\n💰 +${task[5]:.4f}\n👥 ظرفیت: {count}/{task[6]}\n\n'
        'پس از انجام واقعی تسک، دقیقاً دو تصویر بفرست:\n'
        '1️⃣ تصویر نام/صفحه کانال\n2️⃣ تصویر صفحه تسک/انجام موفق',
        reply_markup=kb.as_markup()
    )
    await call.answer()


@dp.callback_query(F.data.startswith('proof:start:'))
async def proof_start(call: CallbackQuery, state: FSMContext):
    tid = int(call.data.split(':')[-1])
    task = await get_task(tid)
    if not task or task[7] != 'active' or await user_has_completion(tid, call.from_user.id):
        return await call.answer('این تسک در دسترس نیست.', show_alert=True)
    await state.clear(); await state.update_data(task_id=tid); await state.set_state(ProofState.first)
    await call.message.answer('📸 اسکرین‌شات اول: تصویر نام/صفحه کانال یا پروفایل مربوط به تسک را بفرست.', reply_markup=cancel_keyboard())
    await call.answer()


@dp.message(ProofState.first, F.photo)
async def proof_first(message: Message, state: FSMContext):
    await state.update_data(proof1=message.photo[-1].file_id)
    await state.set_state(ProofState.second)
    await message.answer('✅ اولی دریافت شد.\n📸 اسکرین‌شات دوم: تصویر صفحه تسک/انجام موفق را بفرست.')


@dp.message(ProofState.second, F.photo)
async def proof_second(message: Message, state: FSMContext):
    d = await state.get_data()
    ok = await create_completion(d['task_id'], message.from_user.id, d['proof1'], message.photo[-1].file_id)
    await state.clear()
    if not ok:
        return await message.answer('این تسک قبلاً برای شما ثبت شده یا ظرفیتش تمام شده است.')
    await message.answer('✅ هر دو اسکرین‌شات ثبت شد و برای بررسی مدیر رفت.')
    task = await get_task(d['task_id'])
    if ADMIN_ID:
        kb = InlineKeyboardBuilder()
        kb.button(text='✅ تایید', callback_data=f'proof:ok:{d["task_id"]}:{message.from_user.id}')
        kb.button(text='❌ رد', callback_data=f'proof:no:{d["task_id"]}:{message.from_user.id}')
        kb.adjust(2)
        await message.bot.send_photo(ADMIN_ID, d['proof1'], caption=f'🧾 مدرک 1 | Task #{d["task_id"]}\nUser: {message.from_user.id}\n{task[3]}')
        await message.bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f'🧾 مدرک 2 | Task #{d["task_id"]}\nReward: ${task[5]:.4f}', reply_markup=kb.as_markup())


@dp.message(ProofState.first)
@dp.message(ProofState.second)
async def proof_not_photo(message: Message):
    await message.answer('لطفاً اسکرین‌شات را به صورت عکس 📸 بفرست.')


@dp.callback_query(F.data.startswith('proof:ok:'))
async def proof_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer('دسترسی ندارید.', show_alert=True)
    _, _, tid, uid = call.data.split(':')
    ok, reward, commission, inviter = await approve_completion(int(tid), int(uid), float(await get_setting('referral_rate', REFERRAL_RATE)))
    if not ok:
        return await call.answer('قبلاً بررسی شده یا ظرفیت تکمیل شده.', show_alert=True)
    await call.answer('تایید شد.')
    try:
        await call.bot.send_message(int(uid), f'🎉 تسک تایید شد!\n💰 +${reward:.4f} به موجودی شما اضافه شد.')
    except Exception:
        pass
    if commission and inviter:
        try:
            await call.bot.send_message(inviter, f'👥 رفرال شما یک تسک تاییدشده انجام داد. +${commission:.4f}')
        except Exception:
            pass


@dp.callback_query(F.data.startswith('proof:no:'))
async def proof_no(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer('دسترسی ندارید.', show_alert=True)
    _, _, tid, uid = call.data.split(':')
    ok = await reject_completion(int(tid), int(uid))
    await call.answer('رد شد.' if ok else 'قبلاً بررسی شده.')
    if ok:
        try:
            await call.bot.send_message(int(uid), '❌ مدارک تسک رد شد. می‌توانی دوباره تسک را انجام بدهی.')
        except Exception:
            pass


# ---------------- CHANNELS ----------------
@dp.callback_query(F.data == 'channels:add')
async def channel_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('مدیریت کانال فقط برای ادمین است.', show_alert=True)
    if await channel_count(call.from_user.id) >= MAX_CHANNELS_PER_USER:
        return await call.answer('حداکثر کانال ثبت شده.', show_alert=True)
    await state.clear(); await state.set_state(ChannelState.network)
    await call.message.answer('شبکه کانال را انتخاب کن:', reply_markup=network_keyboard('channel:net'))
    await call.answer()


@dp.callback_query(F.data.startswith('channel:net:'))
async def channel_network(call: CallbackQuery, state: FSMContext):
    await state.update_data(network=call.data.split(':', 2)[2]); await state.set_state(ChannelState.title)
    await call.message.answer('نام کانال را بفرست:'); await call.answer()


@dp.message(ChannelState.title)
async def channel_title(message: Message, state: FSMContext):
    title = (message.text or '').strip()
    if not title:
        return await message.answer('نام کانال را وارد کن.')
    await state.update_data(title=title); await state.set_state(ChannelState.url)
    await message.answer('لینک کانال را با https:// بفرست:')


@dp.message(ChannelState.url)
async def channel_url(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')):
        return await message.answer('لینک نامعتبر است.')
    d = await state.get_data(); cid = await add_channel(message.from_user.id, d['network'], d['title'], url)
    await state.clear(); await message.answer(f'✅ کانال #{cid} ثبت شد و برای تایید مدیر رفت.')
    if ADMIN_ID:
        kb = InlineKeyboardBuilder(); kb.button(text='✅ تایید', callback_data=f'channel:ok:{cid}'); kb.button(text='❌ رد', callback_data=f'channel:no:{cid}'); kb.adjust(2)
        await message.bot.send_message(ADMIN_ID, f'📢 کانال جدید #{cid}\nUser: {message.from_user.id}\n{d["network"]}\n{d["title"]}\n{url}', reply_markup=kb.as_markup())


@dp.callback_query(F.data == 'channels:list')
async def channels_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('مدیریت کانال فقط برای ادمین است.', show_alert=True)
    rows = await list_user_channels(call.from_user.id)
    if not rows:
        return await call.message.answer('هنوز کانالی ثبت نکرده‌ای.')
    for r in rows:
        kb = InlineKeyboardBuilder(); kb.button(text='✏️ ویرایش لینک', callback_data=f'channel:edit:{r[0]}'); kb.button(text='🗑 حذف', callback_data=f'channel:delete:{r[0]}'); kb.adjust(2)
        await call.message.answer(f'#{r[0]} | {r[2]}\n{r[3]}\n📌 {r[5]}\n{r[4]}', reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data.startswith('channel:delete:'))
async def channel_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('مدیریت کانال فقط برای ادمین است.', show_alert=True)
    cid = int(call.data.split(':')[-1]); ok = await delete_channel(cid, call.from_user.id)
    await call.answer('حذف شد.' if ok else 'یافت نشد.', show_alert=not ok)
    if ok: await call.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith('channel:edit:'))
async def channel_edit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('مدیریت کانال فقط برای ادمین است.', show_alert=True)
    cid = int(call.data.split(':')[-1]); row = await get_user_channel(cid, call.from_user.id)
    if not row: return await call.answer('یافت نشد.', show_alert=True)
    await state.clear(); await state.update_data(channel_id=cid); await state.set_state(ChannelState.edit_url)
    await call.message.answer('لینک جدید را با https:// بفرست:'); await call.answer()


@dp.message(ChannelState.edit_url)
async def channel_edit_url(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')):
        return await message.answer('لینک نامعتبر است.')
    d = await state.get_data(); await update_channel_url(d['channel_id'], message.from_user.id, url); await state.clear()
    await message.answer('✅ لینک تغییر کرد و کانال دوباره برای تایید مدیر رفت.')


@dp.callback_query(F.data.startswith('channel:ok:'))
async def channel_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    cid = int(call.data.split(':')[-1]); await set_channel_status(cid, 'active'); await call.answer('کانال فعال شد.')


@dp.callback_query(F.data.startswith('channel:no:'))
async def channel_no(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    cid = int(call.data.split(':')[-1]); await set_channel_status(cid, 'rejected'); await call.answer('کانال رد شد.')


# ---------------- SUBSCRIBER PURCHASE ----------------

def promo_network_keyboard():
    kb = InlineKeyboardBuilder()
    for n in NETWORKS:
        kb.button(text=f'{n} — ${0:.4f}', callback_data=f'order:network:{n}')
    kb.adjust(2)
    return kb


async def promo_network_keyboard_with_prices():
    kb = InlineKeyboardBuilder()
    for n in NETWORKS:
        price = await get_network_price(n, DEFAULT_SUBSCRIBER_PRICE)
        kb.button(text=f'{n} — ${price:.4f}/عدد', callback_data=f'order:network:{n}')
    kb.adjust(2)
    return kb.as_markup()


@dp.callback_query(F.data == 'promo:start')
async def promo_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OrderState.network)
    kb = await promo_network_keyboard_with_prices()
    lang = await user_lang(call.from_user.id)
    lines = [tr(lang,'promo'), '', tr(lang,'promo_intro'), '']
    for n in NETWORKS:
        price = await get_network_price(n, DEFAULT_SUBSCRIBER_PRICE)
        lines.append(f'• {n}: ${price:.4f} برای هر عدد')
    lines += ['', tr(lang,'order_target'), tr(lang,'promo_payment')]
    await call.message.answer('\n'.join(lines), reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith('order:network:'))
async def order_network(call: CallbackQuery, state: FSMContext):
    network = call.data.split(':', 2)[2]
    if network not in NETWORKS:
        return await call.answer('شبکه نامعتبر است.', show_alert=True)
    price = await get_network_price(network, DEFAULT_SUBSCRIBER_PRICE)
    await state.clear()
    await state.update_data(network=network, price=price)
    await state.set_state(OrderState.target)
    lang = await user_lang(call.from_user.id)
    await call.message.answer(
        f'🌐 {network}\n💵 {tr(lang,"price")}: ${price:.4f} / subscriber\n\n'
        f'{tr(lang,"target")}\nExample: https://t.me/yourchannel',
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(OrderState.target)
async def order_target(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')):
        return await message.answer(tr(await user_lang(message.from_user.id), 'invalid_link'))
    d = await state.get_data()
    await state.update_data(target=url)
    await state.set_state(OrderState.quantity)
    price = float(d['price'])
    kb = InlineKeyboardBuilder()
    for q in [100, 110, 250, 500, 1000]:
        kb.button(text=f'{q} عدد — ${q*price:.2f}', callback_data=f'order:qty:{q}')
    kb.button(text='✏️ تعداد دلخواه', callback_data='order:qty:custom')
    kb.adjust(1)
    await message.answer(
        f'📦 شبکه: {d["network"]}\n🔗 مقصد: {url}\n💵 نرخ: ${price:.4f}/عدد\n\n'
        'تعداد سابسکرایبر را انتخاب کن:',
        reply_markup=kb.as_markup()
    )


@dp.callback_query(F.data.startswith('order:qty:'))
async def order_qty_button(call: CallbackQuery, state: FSMContext):
    value = call.data.split(':')[-1]
    if value == 'custom':
        await call.message.answer(f'تعداد را وارد کن. حداقل {MIN_SUBSCRIBER_QTY} و حداکثر {MAX_SUBSCRIBER_QTY}:', reply_markup=cancel_keyboard())
        await call.answer()
        return
    await create_order_from_quantity(call.message, state, int(value))
    await call.answer()


async def create_order_from_quantity(message: Message, state: FSMContext, q: int):
    if not (MIN_SUBSCRIBER_QTY <= q <= MAX_SUBSCRIBER_QTY):
        return await message.answer(f'تعداد باید بین {MIN_SUBSCRIBER_QTY} تا {MAX_SUBSCRIBER_QTY} باشد.')
    d = await state.get_data()
    total = q * float(d['price'])
    oid, code, total = await create_subscriber_order(message.from_user.id, d['network'], q, d['price'], PAYMENT_WALLET_ADDRESS, d['target'])
    await state.update_data(order_id=oid)
    await state.set_state(OrderState.txid)
    await message.answer(
        f'🧾 سفارش {code}\n'
        f'🌐 شبکه: {d["network"]}\n'
        f'🔗 مقصد: {d["target"]}\n'
        f'👥 تعداد: {q} عدد\n'
        f'💵 نرخ: ${float(d["price"]):.4f} / عدد\n'
        f'💰 مبلغ دقیق: ${total:.8f} USDT\n\n'
        f'💳 آدرس پرداخت USDT BEP20:\n`{PAYMENT_WALLET_ADDRESS}`\n\n'
        '1️⃣ دقیقاً همین مبلغ را با USDT روی شبکه BEP20 به آدرس بالا ارسال کن.\n'
        '2️⃣ بعد از ارسال، TXID تراکنش را همین‌جا بفرست.\n\n'
        '🤖 ربات تراکنش را روی BSC بررسی می‌کند و فقط انتقال موفق USDT با مبلغ دقیق به آدرس پرداخت را قبول می‌کند.\n'
        '⚠️ مبلغ خرید وارد Balance نمی‌شود؛ پرداخت خرید جداست.',
        parse_mode='Markdown', reply_markup=cancel_keyboard()
    )


@dp.message(OrderState.quantity)
async def order_quantity(message: Message, state: FSMContext):
    try:
        q = int((message.text or '').strip())
    except ValueError:
        return await message.answer('❌ تعداد باید عدد باشد. مثال: 110')
    await create_order_from_quantity(message, state, q)


@dp.message(OrderState.txid)
async def order_txid(message: Message, state: FSMContext):
    txid = (message.text or '').strip()
    if not TX_RE.fullmatch(txid):
        return await message.answer('TXID معتبر BSC را بفرست؛ باید با 0x شروع شود و 64 کاراکتر هگز داشته باشد.')
    d = await state.get_data(); order = await get_sub_order(d['order_id'])
    if not order:
        await state.clear(); return await message.answer('سفارش پیدا نشد.')
    if await txid_used(txid):
        return await message.answer('این TXID قبلاً برای یک سفارش استفاده شده است.')
    ok, reason = await verify_bep20_usdt_payment(txid, order[7])
    if not ok:
        return await message.answer(f'⏳ پرداخت هنوز تایید نشد.\n{reason}\n\nاگر تازه پرداخت کردی، کمی صبر کن و همان TXID را دوباره بفرست.')
    if not await mark_sub_order_paid(order[0], txid):
        return await message.answer('این سفارش قبلاً ثبت شده است.')
    await state.clear()
    await message.answer(
        f'✅ پرداخت سفارش {order[1]} تایید شد.\n🧾 {order[1]}\n💰 ${order[7]:.8f} USDT\n\n'
        'پول خرید مستقیماً به آدرس پرداخت سیستم رفته است و وارد Balance شما نمی‌شود.\n'
        'مدیر اکنون سفارش را برای اجرای کمپین بررسی می‌کند.'
    )
    if ADMIN_ID:
        kb = InlineKeyboardBuilder(); kb.button(text='✅ تایید سفارش', callback_data=f'order:ok:{order[0]}'); kb.button(text='❌ رد سفارش', callback_data=f'order:no:{order[0]}'); kb.adjust(2)
        await message.bot.send_message(
            ADMIN_ID,
            f'💰 پرداخت خودکار تایید شد\n🧾 {order[1]}\nUser: {order[2]}\n🌐 {order[4]}\n🔗 {order[9]}\n👥 {order[5]}\n💵 ${order[7]:.8f} USDT\nTXID: {txid}',
            reply_markup=kb.as_markup()
        )


@dp.callback_query(F.data.startswith('order:ok:'))
async def order_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    oid = int(call.data.split(':')[-1]); order = await get_sub_order(oid)
    if not order or not await approve_sub_order(oid): return await call.answer('قبلاً بررسی شده.', show_alert=True)
    await call.answer('سفارش تایید شد.')
    try:
        await call.bot.send_message(order[2], f'✅ سفارش {order[1]} تایید نهایی شد.\n🌐 {order[4]}\n🔗 {order[9]}\n👥 {order[5]} عدد\n💵 ${order[7]:.8f} USDT\n\n📌 مدیر می‌تواند این سفارش را برای ساخت کمپین/تسک اجرا کند.')
    except Exception: pass


@dp.callback_query(F.data.startswith('order:no:'))
async def order_no(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    oid = int(call.data.split(':')[-1]); order = await get_sub_order(oid)
    ok = await reject_sub_order(oid); await call.answer('رد شد.' if ok else 'قبلاً بررسی شده.')
    if ok and order:
        try: await call.bot.send_message(order[2], f'❌ سفارش {order[1]} رد شد. اگر مبلغ ارسال شده، مدیر باید تراکنش را جداگانه بررسی کند.')
        except Exception: pass


# ---------------- WITHDRAWALS ----------------
@dp.callback_query(F.data == 'withdraw:start')
async def withdraw_start(call: CallbackQuery, state: FSMContext):
    u = await get_user(call.from_user.id)
    min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
    balance = float(u[3]) if u else 0.0
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text='💵 USDT BEP20', callback_data='withdraw:method:usdt')
    kb.button(text='❌ لغو', callback_data='cancel')
    kb.adjust(1)
    await call.message.answer(
        f'💸 برداشت\n\n💰 موجودی شما: ${balance:.4f} USDT\n\nحداقل برداشت: ${min_w:.2f}\n\nروش برداشت را انتخاب کن:',
        reply_markup=kb.as_markup()
    )
    await call.answer()


@dp.callback_query(F.data == 'withdraw:method:usdt')
async def withdraw_method(call: CallbackQuery, state: FSMContext):
    u = await get_user(call.from_user.id)
    min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
    balance = float(u[3]) if u else 0.0
    if balance < min_w:
        return await call.answer(f'موجودی شما ${balance:.2f} است؛ حداقل برداشت ${min_w:.2f} است.', show_alert=True)
    await state.clear()
    await state.update_data(method='USDT BEP20')
    await state.set_state(WithdrawState.wallet)
    await call.message.answer(
        f'💵 USDT BEP20 انتخاب شد.\n\n💰 موجودی فعلی: ${balance:.4f} USDT\n\nآدرس کیف پول BEP20 خودت را بفرست.\nمثال: 0x...'
        , reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(Command('withdraw'))
async def withdraw_command(message: Message, state: FSMContext):
    # Keep the command as a shortcut, but use the same safe interactive flow.
    u = await get_user(message.from_user.id)
    min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
    balance = float(u[3]) if u else 0.0
    parts = (message.text or '').split()
    if len(parts) > 1:
        try:
            amount = float(parts[1])
        except ValueError:
            amount = None
        if amount is not None:
            if amount < min_w:
                return await message.answer(f'حداقل برداشت ${min_w:.2f} است.')
            if amount > balance:
                return await message.answer(f'موجودی کافی نیست. موجودی شما ${balance:.4f} USDT است.')
            await state.clear()
            await state.update_data(amount=amount, method='USDT BEP20')
            await state.set_state(WithdrawState.wallet)
            return await message.answer('💵 USDT BEP20\nآدرس کیف پول BEP20 خودت را بفرست:', reply_markup=cancel_keyboard())
    await state.clear()
    kb = InlineKeyboardBuilder(); kb.button(text='💵 USDT BEP20', callback_data='withdraw:method:usdt'); kb.adjust(1)
    await message.answer(f'💸 برداشت\n\n💰 موجودی شما: ${balance:.4f} USDT\nحداقل برداشت: ${min_w:.2f}\n\nروش برداشت را انتخاب کن:', reply_markup=kb.as_markup())


@dp.message(WithdrawState.wallet)
async def withdraw_wallet(message: Message, state: FSMContext):
    wallet = (message.text or '').strip()
    if not HEX40.fullmatch(wallet):
        return await message.answer(tr(await user_lang(message.from_user.id), 'wallet_bad'))
    u = await get_user(message.from_user.id)
    balance = float(u[3]) if u else 0.0
    min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
    if balance < min_w:
        await state.clear()
        return await message.answer(f'❌ موجودی کافی نیست. موجودی شما ${balance:.4f} USDT است؛ حداقل برداشت ${min_w:.2f} است.')
    await state.update_data(wallet=wallet)
    await state.set_state(WithdrawState.amount)
    lang = await user_lang(message.from_user.id)
    await message.answer(
        tr(lang,'address_ok')+f'\n\n'+tr(lang,'balance',balance)+f'\n\n'+tr(lang,'send_amount'),
        reply_markup=cancel_keyboard()
    )


@dp.message(WithdrawState.amount)
async def withdraw_amount(message: Message, state: FSMContext):
    raw = (message.text or '').strip().replace(',', '.')
    try:
        amount = float(raw)
    except ValueError:
        return await message.answer('❌ مقدار صحیح وارد کن. مثال: 2')
    min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
    if amount < min_w:
        return await message.answer(f'❌ حداقل برداشت ${min_w:.2f} است.')
    if amount <= 0:
        return await message.answer('❌ مقدار باید بیشتر از صفر باشد.')

    # Explicit balance check before reserving funds.
    await message.answer(tr(await user_lang(message.from_user.id), 'checking'))
    u = await get_user(message.from_user.id)
    balance = float(u[3]) if u else 0.0
    if amount > balance:
        return await message.answer(tr(await user_lang(message.from_user.id), 'insufficient', balance, amount))

    d = await state.get_data()
    wid = await create_withdrawal(message.from_user.id, amount, d['wallet'])
    if not wid:
        return await message.answer('❌ هنگام رزرو موجودی خطا رخ داد؛ موجودی شما کم نشده است.')
    await state.clear()
    await message.answer(
        f'✅ درخواست برداشت ثبت شد.\n\n🧾 شماره: #{wid}\n💰 مبلغ: ${amount:.2f} USDT\n🌐 شبکه: BEP20\n💳 آدرس: {d["wallet"]}\n\n⏳ مبلغ از موجودی شما رزرو شد و در انتظار پرداخت مدیر است.'
    )
    if ADMIN_ID:
        kb = InlineKeyboardBuilder()
        kb.button(text='💸 پرداخت + TXID', callback_data=f'wd:pay:{wid}')
        kb.button(text='❌ رد و برگشت موجودی', callback_data=f'wd:no:{wid}')
        kb.adjust(2)
        await message.bot.send_message(
            ADMIN_ID,
            f'💸 برداشت جدید #{wid}\nUser: {message.from_user.id}\nAmount: ${amount:.2f} USDT\nWallet: {d["wallet"]}',
            reply_markup=kb.as_markup()
        )


@dp.callback_query(F.data.startswith('wd:pay:'))
async def withdraw_pay(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    wid = int(call.data.split(':')[-1]); row = await get_withdrawal(wid)
    if not row or row[4] != 'pending': return await call.answer('درخواست دیگر در انتظار نیست.', show_alert=True)
    await state.clear(); await state.update_data(wid=wid); await state.set_state(WithdrawState.txid)
    await call.message.answer(f'برداشت #{wid}\nTXID پرداختی که خودت در BSC فرستادی را بفرست:'); await call.answer()


@dp.message(WithdrawState.txid)
async def withdraw_txid(message: Message, state: FSMContext):
    txid = (message.text or '').strip()
    if not TX_RE.fullmatch(txid): return await message.answer('TXID معتبر BSC را بفرست.')
    d = await state.get_data(); await state.update_data(txid=txid); await state.set_state(WithdrawState.receipt)
    await message.answer('حالا یک اسکرین‌شات رسید پرداخت را بفرست 📸')


@dp.message(WithdrawState.receipt, F.photo)
async def withdraw_receipt(message: Message, state: FSMContext):
    d = await state.get_data(); row = await get_withdrawal(d['wid'])
    if not row or row[4] != 'pending':
        await state.clear(); return await message.answer('این برداشت قبلاً بررسی شده است.')
    ok = await approve_withdrawal(d['wid'], d['txid'], message.photo[-1].file_id)
    await state.clear()
    if not ok: return await message.answer('این برداشت قبلاً بررسی شده است.')
    await message.answer('✅ برداشت پرداخت‌شده ثبت شد و رسید برای کاربر ارسال می‌شود.')
    try:
        await message.bot.send_photo(row[1], message.photo[-1].file_id, caption=f'✅ برداشت #{row[0]} پرداخت شد.\n💰 ${row[2]:.2f} USDT\n🌐 BEP20\nTXID: {d["txid"]}')
    except Exception: pass


@dp.message(WithdrawState.receipt)
async def withdraw_receipt_nonphoto(message: Message, state: FSMContext):
    await message.answer('لطفاً رسید را به صورت عکس 📸 بفرست.')


@dp.callback_query(F.data.startswith('wd:no:'))
async def withdraw_no(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    wid = int(call.data.split(':')[-1]); ok = await reject_withdrawal(wid); await call.answer('رد و برگشت موجودی.' if ok else 'قبلاً بررسی شده.')


# ---------------- ADMIN ----------------
@dp.message(Command('unblockme'))
async def unblock_me(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer('دسترسی ندارید.')
    await set_blocked(message.from_user.id, False)
    await message.answer('✅ حساب مدیر رفع مسدودی شد.', reply_markup=user_menu((await user_lang(message.from_user.id)), True))


@dp.message(Command('admin'))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id): return await message.answer('دسترسی ندارید.')
    await message.answer('👑 پنل مدیریت', reply_markup=admin_keyboard())


@dp.callback_query(F.data.startswith('admin:'))
async def admin_router(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    action = call.data.split(':', 1)[1]
    if action.startswith('chstatus:'):
        _, cid, status = action.split(':')
        await set_channel_status(int(cid), status)
        await call.answer('تغییر کرد.')
        return
    if action == 'dash':
        users, tasks, withdrawals, channels = await dashboard_stats()
        await call.message.answer(f'📊 داشبورد\n👥 کاربران: {users}\n🔥 تسک‌ها: {tasks}\n📢 کانال‌ها: {channels}\n💸 برداشت‌های پرداخت‌شده: ${withdrawals:.2f}')
    elif action == 'addtask':
        await state.clear(); await state.set_state(TaskState.network); await call.message.answer('شبکه تسک را انتخاب کن:', reply_markup=network_keyboard('task:net'))
    elif action == 'tasks':
        rows = await admin_tasks()
        if not rows: await call.message.answer('هنوز تسکی نیست.')
        for r in rows:
            kb = InlineKeyboardBuilder(); kb.button(text='⏸ خاموش' if r[6] == 'active' else '▶️ فعال', callback_data=f'task:toggle:{r[0]}:{"inactive" if r[6]=="active" else "active"}')
            await call.message.answer(f'#{r[0]} | {r[1]}\n{r[2]}\n💰 ${r[4]:.4f}\n👥 {r[7]}/{r[5]}\n📌 {r[6]}', reply_markup=kb.as_markup())
    elif action == 'proofs':
        rows = await pending_completions()
        await call.message.answer(f'🧾 مدارک در انتظار: {len(rows)}')
        for r in rows:
            await call.message.answer(f'#{r[1]} | User {r[2]} | {r[6]} | ${r[7]:.4f}\nدو تصویر به پیام‌های بعدی مدیر ارسال شده‌اند.')
    elif action == 'channels':
        rows = await all_channels()
        if not rows: await call.message.answer('کانالی نیست.')
        for r in rows:
            kb = InlineKeyboardBuilder()
            if r[5] == 'active': kb.button(text='⛔ غیرفعال', callback_data=f'admin:chstatus:{r[0]}:rejected')
            else: kb.button(text='✅ فعال', callback_data=f'admin:chstatus:{r[0]}:active')
            await call.message.answer(f'#{r[0]} User:{r[1]}\n{r[2]} | {r[3]}\n{r[4]}\n📌 {r[5]}', reply_markup=kb.as_markup())
    elif action == 'users':
        rows = await users_list()
        if not rows: await call.message.answer('کاربری نیست.')
        for r in rows:
            kb = InlineKeyboardBuilder(); kb.button(text='🚫 مسدود' if not r[3] else '✅ رفع مسدودی', callback_data=f'user:block:{r[0]}:{0 if r[3] else 1}'); kb.button(text='💰 موجودی', callback_data=f'user:bal:{r[0]}'); kb.adjust(2)
            await call.message.answer(f'👤 {r[0]} @{r[1] or "-"}\n💰 ${r[2]:.4f}\n📌 {"BLOCKED" if r[3] else "ACTIVE"}', reply_markup=kb.as_markup())
    elif action == 'orders':
        rows = await pending_sub_orders()
        if not rows: await call.message.answer('سفارش در انتظار نیست.')
        for r in rows:
            await call.message.answer(f'🛒 {r[1]} | User {r[2]}\n🌐 {r[4]} | 👥 {r[5]}\n🔗 مقصد: {r[9] or "-"}\n💵 نرخ: ${r[6]:.4f}/عدد\n💰 مبلغ: ${r[7]:.8f} USDT\nTXID: {r[10] or "-"}\nStatus: {r[11]}')
    elif action == 'withdrawals':
        rows = await pending_withdrawals()
        if not rows: await call.message.answer('برداشت در انتظار نیست.')
        for r in rows:
            await call.message.answer(f'💸 #{r[0]} User:{r[1]}\n💰 ${r[2]:.2f} USDT\nWallet:{r[3]}')
    elif action == 'prices':
        kb = InlineKeyboardBuilder()
        for n in NETWORKS: kb.button(text=f'{n}: ${await get_network_price(n):.4f}', callback_data=f'price:set:{n}')
        kb.adjust(2)
        await call.message.answer('💵 قیمت هر سابسکرایبر را برای هر شبکه جداگانه تغییر بده:', reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data.startswith('task:net:'))
async def admin_task_network(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    await state.update_data(network=call.data.split(':', 2)[2]); await state.set_state(TaskState.title); await call.message.answer('عنوان تسک:'); await call.answer()


@dp.message(TaskState.title)
async def admin_task_title(message: Message, state: FSMContext):
    await state.update_data(title=(message.text or '').strip()); await state.set_state(TaskState.url); await message.answer('لینک تسک:')


@dp.message(TaskState.url)
async def admin_task_url(message: Message, state: FSMContext):
    url = (message.text or '').strip()
    if not url.startswith(('http://', 'https://')): return await message.answer('لینک نامعتبر است.')
    await state.update_data(url=url); await state.set_state(TaskState.reward); await message.answer('پاداش هر انجام موفق (دلار): مثال 0.02')


@dp.message(TaskState.reward)
async def admin_task_reward(message: Message, state: FSMContext):
    try:
        reward = float(message.text.strip())
        if reward <= 0: raise ValueError
    except ValueError: return await message.answer('مبلغ نامعتبر است.')
    await state.update_data(reward=reward); await state.set_state(TaskState.limit); await message.answer('ظرفیت تسک را بفرست. مثال 250:')


@dp.message(TaskState.limit)
async def admin_task_limit(message: Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        if limit <= 0: raise ValueError
    except ValueError: return await message.answer('ظرفیت باید عدد مثبت باشد.')
    d = await state.get_data(); tid = await create_task(ADMIN_ID, d['network'], d['title'], d['url'], d['reward'], limit); await state.clear()
    task = await get_task(tid); sent = await broadcast_new_task(message.bot, task)
    await message.answer(f'✅ تسک #{tid} ساخته شد و برای {sent} کاربر فعال اطلاع‌رسانی شد.')


@dp.callback_query(F.data.startswith('task:toggle:'))
async def task_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    _, _, tid, status = call.data.split(':'); await set_task_status(int(tid), status); await call.answer('وضعیت تغییر کرد.')


@dp.callback_query(F.data.startswith('user:block:'))
async def admin_user_block(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    _, _, uid, value = call.data.split(':')
    target_uid = int(uid)
    if target_uid == ADMIN_ID:
        return await call.answer('👑 ادمین اصلی قابل مسدود شدن نیست.', show_alert=True)
    await set_blocked(target_uid, bool(int(value)))
    await call.answer('انجام شد.')


@dp.callback_query(F.data.startswith('user:bal:'))
async def admin_user_balance(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    uid = int(call.data.split(':')[-1]); await state.clear(); await state.update_data(user_id=uid); await state.set_state(BalanceState.amount)
    await call.message.answer('تغییر موجودی را بفرست. مثبت = اضافه، منفی = کم. مثال: 2.5'); await call.answer()


@dp.message(BalanceState.amount)
async def admin_user_balance_amount(message: Message, state: FSMContext):
    try: amount = float(message.text.strip())
    except ValueError: return await message.answer('عدد نامعتبر است.')
    d = await state.get_data(); await adjust_balance(d['user_id'], amount); await state.clear(); await message.answer('✅ موجودی تغییر کرد.')


@dp.callback_query(F.data.startswith('price:set:'))
async def price_set(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer('دسترسی ندارید.', show_alert=True)
    network = call.data.split(':', 2)[2]; await state.clear(); await state.update_data(network=network); await state.set_state(PriceState.price)
    await call.message.answer(f'قیمت جدید هر سابسکرایبر برای {network} را بفرست. مثال 0.01 یا 0.02 یا 0.05:', reply_markup=cancel_keyboard()); await call.answer()


@dp.message(PriceState.price)
async def price_save(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
        if not (MIN_SUBSCRIBER_PRICE <= price <= MAX_SUBSCRIBER_PRICE): raise ValueError
    except ValueError:
        return await message.answer(f'قیمت باید بین {MIN_SUBSCRIBER_PRICE} و {MAX_SUBSCRIBER_PRICE} باشد.')
    d = await state.get_data(); await set_setting(f'price_{d["network"]}', price); await state.clear(); await message.answer(f'✅ قیمت {d["network"]}: ${price:.4f} برای هر سابسکرایبر')


# ---------------- MENU ----------------
@dp.callback_query(F.data == 'cancel')
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear(); await call.message.answer('لغو شد.'); await call.answer()


@dp.message()
async def router(message: Message):
    u = await ensure_user(message)
    if u[6] and not is_admin(message.from_user.id): return await message.answer(tr(u[2], 'blocked'))
    lang = u[2] if u[2] in TEXT else 'fa'; t = TEXT[lang]
    if message.text == t['balance']:
        await message.answer(tr(lang, 'balance', u[3]))
    elif message.text == t['profile']:
        me = await message.bot.get_me()
        ref_link = f'https://t.me/{me.username}?start=ref_{u[4]}' if me.username else f'ref_{u[4]}'
        await message.answer((f'👤 @{u[1] or "user"}\n🆔 {u[0]}\n'+tr(lang,'balance',u[3])+f'\n\n🎁 Referral Code: {u[4]}\n🔗 Referral Link: {ref_link}\n{tr(lang,'referral_commission')}'))
    elif message.text == t['tasks']:
        rows = await available_tasks(message.from_user.id)
        if not rows: return await message.answer(tr(lang, 'tasks_empty'))
        for r in rows:
            kb = InlineKeyboardBuilder(); kb.button(text='🔥 انجام تسک', callback_data=f'task:open:{r[0]}')
            await message.answer(f'#{r[0]} | {r[1]}\n📝 {r[2]}\n💰 +${r[4]:.4f}\n👥 {r[7]}/{r[5]}', reply_markup=kb.as_markup())
    elif message.text == t['referral']:
        me = await message.bot.get_me()
        ref_link = f'https://t.me/{me.username}?start=ref_{u[4]}' if me.username else f'ref_{u[4]}'
        if lang == 'en':
            text = f'👥 Referral Code: {u[4]}\n💵 Commission: 10% of the invited user task reward\n\n🔗 Referral Link:\n{ref_link}'
        elif lang == 'hi':
            text = f'👥 रेफरल कोड: {u[4]}\n💵 कमीशन: आमंत्रित उपयोगकर्ता के टास्क रिवॉर्ड का 10%\n\n🔗 रेफरल लिंक:\n{ref_link}'
        else:
            text = f'👥 کد رفرال شما: {u[4]}\n💵 کمیسیون: ۱۰٪ از پاداش تسک کاربر دعوت‌شده\n\n🔗 لینک دعوت:\n{ref_link}'
        await message.answer(text)
    elif message.text == t['rank']:
        out = tr(lang, 'rank')+'\n'
        for i, r in enumerate(await leaderboard(), 1): out += f'\n{i}. @{r[1] or r[0]} — {r[2]} تسک'
        await message.answer(out)
    elif message.text == t['withdraw']:
        min_w = float(await get_setting('min_withdraw', MIN_WITHDRAW))
        kb = InlineKeyboardBuilder(); kb.button(text='💵 USDT BEP20', callback_data='withdraw:method:usdt'); kb.adjust(1)
        await message.answer(f'💸 برداشت\n\n💰 موجودی: ${u[3]:.4f} USDT\nحداقل برداشت: ${min_w:.2f}\n\nChoose Withdraw Method:', reply_markup=kb.as_markup())
    elif message.text == t['promo']:
        await message.answer('🛒 خرید سابسکرایبر\n\nشبکه را انتخاب کن، نرخ هر شبکه را ببین، لینک مقصد را وارد کن و تعداد را انتخاب کن. پرداخت خرید با USDT BEP20 مستقیم به آدرس پرداخت سیستم انجام می‌شود و وارد Balance نمی‌شود.', reply_markup=InlineKeyboardBuilder().button(text='🛒 شروع سفارش', callback_data='promo:start').as_markup())
    elif message.text == t['language']:
        await message.answer(tr(lang, 'lang_prompt'), reply_markup=language_keyboard())
    elif is_admin(message.from_user.id) and message.text == t['admin']:
        await message.answer('👑 پنل مدیریت', reply_markup=admin_keyboard())
    else:
        await message.answer('از منو استفاده کن 👇', reply_markup=user_menu(lang, is_admin(message.from_user.id)))


async def main():
    await init_db()
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN تنظیم نشده است. آن را در Railway Variables قرار بده.')
    if not HEX40.fullmatch(PAYMENT_WALLET_ADDRESS):
        raise RuntimeError('PAYMENT_WALLET_ADDRESS نامعتبر است.')
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
