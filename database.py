import os
import secrets
from datetime import datetime, timedelta
import aiosqlite

DB_NAME = os.getenv('DB_NAME', 'taskly.sqlite3').strip()


def now():
    return datetime.utcnow().isoformat()


async def init_db():
    parent = os.path.dirname(DB_NAME)
    if parent:
        os.makedirs(parent, exist_ok=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            language TEXT DEFAULT 'fa',
            balance REAL DEFAULT 0,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            is_blocked INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS channels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            network TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            network TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            reward REAL NOT NULL,
            max_users INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_completions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            proof1 TEXT NOT NULL,
            proof2 TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            UNIQUE(task_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            asset TEXT DEFAULT 'USDT',
            network TEXT DEFAULT 'BEP20',
            wallet_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            txid TEXT,
            receipt_file_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscriber_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL DEFAULT 0,
            target_url TEXT,
            network TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            payment_wallet TEXT NOT NULL,
            txid TEXT UNIQUE,
            status TEXT DEFAULT 'awaiting_payment',
            created_at TEXT NOT NULL,
            paid_at TEXT
        );
        CREATE TABLE IF NOT EXISTS referrals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            invited_id INTEGER UNIQUE NOT NULL,
            commission_rate REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        ''')
        cols = [r[1] for r in await (await db.execute('PRAGMA table_info(subscriber_orders)')).fetchall()]
        if 'target_url' not in cols:
            await db.execute('ALTER TABLE subscriber_orders ADD COLUMN target_url TEXT')
        await db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('min_withdraw', '2.00'))
        await db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('referral_rate', '0.10'))
        for network in ['YouTube','Instagram','TikTok','Telegram','Facebook','X']:
            await db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (f'price_{network}', '0.02'))
        await db.commit()


async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute('SELECT value FROM settings WHERE key=?', (key,))).fetchone()
        return row[0] if row else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
        await db.commit()


async def get_network_price(network, default=0.02):
    return float(await get_setting(f'price_{network}', default))


async def get_user(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT telegram_id,username,language,balance,referral_code,referred_by,is_blocked,created_at FROM users WHERE telegram_id=?', (uid,))).fetchone()


async def all_user_ids():
    async with aiosqlite.connect(DB_NAME) as db:
        return [r[0] for r in await (await db.execute('SELECT telegram_id FROM users WHERE is_blocked=0')).fetchall()]


async def create_user(uid, username, code, referred_by=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT OR IGNORE INTO users(telegram_id,username,referral_code,referred_by,created_at) VALUES(?,?,?,?,?)', (uid, username or '', code, referred_by, now()))
        await db.commit()


async def update_username(uid, username):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET username=? WHERE telegram_id=?', (username or '', uid))
        await db.commit()


async def set_language(uid, language):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET language=? WHERE telegram_id=?', (language, uid))
        await db.commit()


async def set_blocked(uid, blocked):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET is_blocked=? WHERE telegram_id=?', (1 if blocked else 0, uid))
        await db.commit()


async def adjust_balance(uid, amount, note='admin adjustment'):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (amount, uid))
        await db.execute('INSERT INTO ledger(user_id,amount,type,note,created_at) VALUES(?,?,?,?,?)', (uid, amount, 'admin_adjustment', note, now()))
        await db.commit()


async def get_user_by_referral_code(code):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT telegram_id FROM users WHERE referral_code=?', (code,))).fetchone()


async def create_referral(inviter, invited, rate):
    if inviter == invited:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT OR IGNORE INTO referrals(inviter_id,invited_id,commission_rate,created_at) VALUES(?,?,?,?)', (inviter, invited, rate, now()))
        await db.commit()


async def channel_count(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return (await (await db.execute('SELECT COUNT(*) FROM channels WHERE user_id=?', (uid,))).fetchone())[0]


async def add_channel(uid, network, title, url):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('INSERT INTO channels(user_id,network,title,url,created_at) VALUES(?,?,?,?,?)', (uid, network, title, url, now()))
        await db.commit()
        return cur.lastrowid


async def list_user_channels(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,user_id,network,title,url,status,created_at FROM channels WHERE user_id=? ORDER BY id DESC', (uid,))).fetchall()


async def active_user_channels(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT id,user_id,network,title,url,status,created_at FROM channels WHERE user_id=? AND status='active' ORDER BY id DESC", (uid,))).fetchall()


async def get_user_channel(cid, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,user_id,network,title,url,status,created_at FROM channels WHERE id=? AND user_id=?', (cid, uid))).fetchone()


async def delete_channel(cid, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('DELETE FROM channels WHERE id=? AND user_id=?', (cid, uid))
        await db.commit()
        return cur.rowcount > 0


async def update_channel_url(cid, uid, url):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE channels SET url=?,status='pending' WHERE id=? AND user_id=?", (url, cid, uid))
        await db.commit()
        return cur.rowcount > 0


async def pending_channels():
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT id,user_id,network,title,url,status,created_at FROM channels WHERE status='pending' ORDER BY id ASC")).fetchall()


async def all_channels(limit=100):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,user_id,network,title,url,status,created_at FROM channels ORDER BY id DESC LIMIT ?', (limit,))).fetchall()


async def set_channel_status(cid, status):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('UPDATE channels SET status=? WHERE id=?', (status, cid))
        await db.commit()
        return cur.rowcount > 0


async def create_task(owner_id, network, title, url, reward, max_users):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('INSERT INTO tasks(owner_id,network,title,url,reward,max_users,created_at) VALUES(?,?,?,?,?,?,?)', (owner_id, network, title, url, reward, max_users, now()))
        await db.commit()
        return cur.lastrowid


async def get_task(tid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,owner_id,network,title,url,reward,max_users,status,created_at FROM tasks WHERE id=?', (tid,))).fetchone()


async def approved_count(tid):
    async with aiosqlite.connect(DB_NAME) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM task_completions WHERE task_id=? AND status='approved'", (tid,))).fetchone())[0]


async def user_has_completion(tid, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return (await (await db.execute("SELECT 1 FROM task_completions WHERE task_id=? AND user_id=? AND status IN ('pending','approved')", (tid, uid))).fetchone()) is not None


async def available_tasks(uid, network=None):
    q = '''SELECT t.id,t.network,t.title,t.url,t.reward,t.max_users,t.status,
           (SELECT COUNT(*) FROM task_completions c WHERE c.task_id=t.id AND c.status IN ('pending','approved')) AS used
           FROM tasks t
           WHERE t.status='active'
           AND (SELECT COUNT(*) FROM task_completions c2 WHERE c2.task_id=t.id AND c2.status IN ('pending','approved')) < t.max_users
           AND NOT EXISTS(SELECT 1 FROM task_completions c3 WHERE c3.task_id=t.id AND c3.user_id=? AND c3.status IN ('pending','approved'))'''
    args = [uid]
    if network:
        q += ' AND t.network=?'
        args.append(network)
    q += ' ORDER BY t.id DESC LIMIT 100'
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute(q, args)).fetchall()


async def admin_tasks(limit=100):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT t.id,t.network,t.title,t.url,t.reward,t.max_users,t.status,(SELECT COUNT(*) FROM task_completions c WHERE c.task_id=t.id AND c.status='approved') FROM tasks t ORDER BY t.id DESC LIMIT ?", (limit,))).fetchall()


async def set_task_status(tid, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE tasks SET status=? WHERE id=?', (status, tid))
        await db.commit()


async def create_completion(tid, uid, proof1, proof2):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('BEGIN IMMEDIATE')
        task = await (await db.execute('SELECT max_users,status FROM tasks WHERE id=?', (tid,))).fetchone()
        if not task or task[1] != 'active':
            await db.rollback()
            return False
        cnt = (await (await db.execute("SELECT COUNT(*) FROM task_completions WHERE task_id=? AND status IN ('pending','approved')", (tid,))).fetchone())[0]
        if cnt >= task[0]:
            await db.rollback()
            return False
        try:
            await db.execute("INSERT INTO task_completions(task_id,user_id,proof1,proof2,status,created_at) VALUES(?,?,?,?,'pending',?)", (tid, uid, proof1, proof2, now()))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            await db.rollback()
            return False


async def get_completion(tid, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,task_id,user_id,proof1,proof2,status,created_at FROM task_completions WHERE task_id=? AND user_id=?', (tid, uid))).fetchone()


async def pending_completions(limit=50):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT c.id,c.task_id,c.user_id,c.proof1,c.proof2,c.created_at,t.title,t.reward,t.network FROM task_completions c JOIN tasks t ON t.id=c.task_id WHERE c.status='pending' ORDER BY c.id ASC LIMIT ?", (limit,))).fetchall()


async def approve_completion(tid, uid, ref_rate):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('BEGIN IMMEDIATE')
        c = await (await db.execute("SELECT id,status FROM task_completions WHERE task_id=? AND user_id=?", (tid, uid))).fetchone()
        task = await (await db.execute('SELECT reward,max_users FROM tasks WHERE id=?', (tid,))).fetchone()
        if not c or c[1] != 'pending' or not task:
            await db.rollback()
            return False, 0, 0, None
        count = (await (await db.execute("SELECT COUNT(*) FROM task_completions WHERE task_id=? AND status='approved'", (tid,))).fetchone())[0]
        if count >= task[1]:
            await db.rollback()
            return False, 0, 0, None
        reward = float(task[0])
        await db.execute("UPDATE task_completions SET status='approved' WHERE id=?", (c[0],))
        await db.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (reward, uid))
        await db.execute('INSERT INTO ledger(user_id,amount,type,note,created_at) VALUES(?,?,?,?,?)', (uid, reward, 'task_reward', f'task:{tid}', now()))
        inviter = await (await db.execute('SELECT inviter_id,commission_rate FROM referrals WHERE invited_id=?', (uid,))).fetchone()
        commission = 0.0
        inviter_id = None
        if inviter:
            commission = reward * float(inviter[1])
            inviter_id = inviter[0]
            await db.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (commission, inviter_id))
            await db.execute('INSERT INTO ledger(user_id,amount,type,note,created_at) VALUES(?,?,?,?,?)', (inviter_id, commission, 'referral_commission', f'user:{uid}/task:{tid}', now()))
        await db.commit()
        return True, reward, commission, inviter_id


async def reject_completion(tid, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE task_completions SET status='rejected' WHERE task_id=? AND user_id=? AND status='pending'", (tid, uid))
        await db.commit()
        return cur.rowcount > 0


async def create_withdrawal(uid, amount, address):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('BEGIN IMMEDIATE')
        user = await (await db.execute('SELECT balance FROM users WHERE telegram_id=?', (uid,))).fetchone()
        if not user or float(user[0]) < amount:
            await db.rollback()
            return None
        await db.execute('UPDATE users SET balance=balance-? WHERE telegram_id=?', (amount, uid))
        cur = await db.execute('INSERT INTO withdrawals(user_id,amount,asset,network,wallet_address,status,created_at) VALUES(?,?,?,?,?,"pending",?)', (uid, amount, 'USDT', 'BEP20', address, now()))
        wid = cur.lastrowid
        await db.execute('INSERT INTO ledger(user_id,amount,type,note,created_at) VALUES(?,?,?,?,?)', (uid, -amount, 'withdraw_hold', f'withdrawal:{wid}', now()))
        await db.commit()
        return wid


async def pending_withdrawals(limit=50):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT id,user_id,amount,wallet_address,status,txid,receipt_file_id,created_at FROM withdrawals WHERE status='pending' ORDER BY id ASC LIMIT ?", (limit,))).fetchall()


async def get_withdrawal(wid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT id,user_id,amount,wallet_address,status,txid,receipt_file_id,created_at FROM withdrawals WHERE id=?", (wid,))).fetchone()


async def approve_withdrawal(wid, txid, receipt_file_id=None):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE withdrawals SET status='paid',txid=?,receipt_file_id=? WHERE id=? AND status='pending'", (txid, receipt_file_id, wid))
        await db.commit()
        return cur.rowcount > 0


async def reject_withdrawal(wid):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('BEGIN IMMEDIATE')
        row = await (await db.execute("SELECT user_id,amount FROM withdrawals WHERE id=? AND status='pending'", (wid,))).fetchone()
        if not row:
            await db.rollback()
            return False
        uid, amount = row
        await db.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
        await db.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (amount, uid))
        await db.execute('INSERT INTO ledger(user_id,amount,type,note,created_at) VALUES(?,?,?,?,?)', (uid, amount, 'withdraw_return', f'withdrawal:{wid}', now()))
        await db.commit()
        return True


async def create_subscriber_order(uid, network, quantity, unit_price, wallet, target_url):
    code = 'SUB-' + secrets.token_hex(4).upper()
    total = round(quantity * unit_price, 8)
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('INSERT INTO subscriber_orders(order_code,user_id,channel_id,target_url,network,quantity,unit_price,total,payment_wallet,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)', (code, uid, 0, target_url, network, quantity, unit_price, total, wallet, now()))
        await db.commit()
        return cur.lastrowid, code, total


async def get_sub_order(oid):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,order_code,user_id,channel_id,network,quantity,unit_price,total,payment_wallet,target_url,txid,status,created_at,paid_at FROM subscriber_orders WHERE id=?', (oid,))).fetchone()


async def get_sub_order_by_code(code):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT id,order_code,user_id,channel_id,network,quantity,unit_price,total,payment_wallet,target_url,txid,status,created_at,paid_at FROM subscriber_orders WHERE order_code=?', (code,))).fetchone()


async def pending_sub_orders(limit=100):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT id,order_code,user_id,channel_id,network,quantity,unit_price,total,payment_wallet,target_url,txid,status,created_at,paid_at FROM subscriber_orders WHERE status IN ('awaiting_payment','paid_pending_review') ORDER BY id ASC LIMIT ?", (limit,))).fetchall()


async def mark_sub_order_paid(oid, txid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE subscriber_orders SET txid=?,status='paid_pending_review',paid_at=? WHERE id=? AND status='awaiting_payment'", (txid, now(), oid))
        await db.commit()
        return cur.rowcount > 0


async def approve_sub_order(oid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE subscriber_orders SET status='approved' WHERE id=? AND status='paid_pending_review'", (oid,))
        await db.commit()
        return cur.rowcount > 0


async def reject_sub_order(oid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("UPDATE subscriber_orders SET status='rejected' WHERE id=? AND status IN ('awaiting_payment','paid_pending_review')", (oid,))
        await db.commit()
        return cur.rowcount > 0


async def txid_used(txid):
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute('SELECT 1 FROM subscriber_orders WHERE txid=?', (txid,))).fetchone()
        return row is not None


async def leaderboard():
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute("SELECT u.telegram_id,u.username,COUNT(c.id) FROM users u LEFT JOIN task_completions c ON c.user_id=u.telegram_id AND c.status='approved' AND c.created_at>=? GROUP BY u.telegram_id ORDER BY COUNT(c.id) DESC LIMIT 20", (since,))).fetchall()


async def users_list(limit=100):
    async with aiosqlite.connect(DB_NAME) as db:
        return await (await db.execute('SELECT telegram_id,username,balance,is_blocked,created_at FROM users ORDER BY telegram_id DESC LIMIT ?', (limit,))).fetchall()


async def dashboard_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        users = (await (await db.execute('SELECT COUNT(*) FROM users')).fetchone())[0]
        tasks = (await (await db.execute('SELECT COUNT(*) FROM tasks')).fetchone())[0]
        withdrawals = float((await (await db.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='paid'")).fetchone())[0])
        channels = (await (await db.execute('SELECT COUNT(*) FROM channels')).fetchone())[0]
        return users, tasks, withdrawals, channels
