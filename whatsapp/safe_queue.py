from __future__ import annotations
import os,sqlite3,threading,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
DB_PATH=os.getenv("SAFE_QUEUE_DB",str(BASE_DIR/"data"/"safe_queue.db"))
ACTIVE_WINDOW_HOURS=int(os.getenv("SAFE_ACTIVE_WINDOW_HOURS","24"))
MIN_DELAY_SECONDS=float(os.getenv("SAFE_MIN_DELAY_SECONDS","8"))
MAX_DELAY_SECONDS=float(os.getenv("SAFE_MAX_DELAY_SECONDS","20"))
_lock=threading.RLock()
def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat()
def connect():
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH,check_same_thread=False); c.row_factory=sqlite3.Row; return c
def init_db():
    with _lock:
        c=connect(); c.executescript("""
        CREATE TABLE IF NOT EXISTS contacts(phone TEXT PRIMARY KEY,name TEXT DEFAULT '',opt_in INTEGER NOT NULL DEFAULT 0,conversation_active INTEGER NOT NULL DEFAULT 0,last_incoming_at TEXT,last_outgoing_at TEXT,total_incoming INTEGER NOT NULL DEFAULT 0,total_outgoing INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY,phone TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',reason TEXT DEFAULT '',created_at TEXT NOT NULL,started_at TEXT,sent_at TEXT,error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,phone TEXT,event_type TEXT NOT NULL,detail TEXT DEFAULT '',created_at TEXT NOT NULL);
        """); c.commit(); c.close()
def event(c,phone,typ,detail=''): c.execute('INSERT INTO events(phone,event_type,detail,created_at) VALUES(?,?,?,?)',(phone,typ,detail,iso(now())))
def upsert_contact(phone,name='',opt_in=False):
    phone=str(phone).strip()
    if not phone: raise ValueError('phone obrigatório')
    with _lock:
        c=connect(); t=iso(now()); c.execute("""INSERT INTO contacts(phone,name,opt_in,updated_at) VALUES(?,?,?,?) ON CONFLICT(phone) DO UPDATE SET name=excluded.name,opt_in=excluded.opt_in,updated_at=excluded.updated_at""",(phone,name,int(opt_in),t)); c.commit(); c.close()
def register_incoming(phone,name='',text=''):
    phone=str(phone).strip(); t=iso(now())
    if not phone: raise ValueError('phone obrigatório')
    with _lock:
        c=connect(); c.execute("""INSERT INTO contacts(phone,name,conversation_active,last_incoming_at,total_incoming,updated_at) VALUES(?,?,1,?,1,?) ON CONFLICT(phone) DO UPDATE SET name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE contacts.name END,conversation_active=1,last_incoming_at=excluded.last_incoming_at,total_incoming=contacts.total_incoming+1,updated_at=excluded.updated_at""",(phone,name,t,t)); event(c,phone,'incoming',text[:500]); c.commit(); c.close()
def expire_inactive():
    cutoff=now()-timedelta(hours=ACTIVE_WINDOW_HOURS)
    with _lock:
        c=connect(); rows=c.execute("SELECT phone,last_incoming_at FROM contacts WHERE conversation_active=1 AND last_incoming_at IS NOT NULL").fetchall()
        for r in rows:
            try:
                if datetime.fromisoformat(r['last_incoming_at'])<cutoff: c.execute('UPDATE contacts SET conversation_active=0,updated_at=? WHERE phone=?',(iso(now()),r['phone'])); event(c,r['phone'],'conversation_expired',f'Janela de {ACTIVE_WINDOW_HOURS}h expirada')
            except Exception: pass
        c.commit(); c.close()
def enqueue(phone,message,require_active=True):
    phone,message=str(phone).strip(),str(message).strip(); expire_inactive()
    with _lock:
        c=connect(); r=c.execute('SELECT * FROM contacts WHERE phone=?',(phone,)).fetchone()
        if not r: c.close(); return {'accepted':False,'reason':'contato_nao_cadastrado'}
        if not r['opt_in']: event(c,phone,'blocked','Sem opt-in explícito'); c.commit(); c.close(); return {'accepted':False,'reason':'sem_opt_in'}
        if require_active and not r['conversation_active']: event(c,phone,'blocked','Conversa inativa'); c.commit(); c.close(); return {'accepted':False,'reason':'conversa_inativa'}
        q=str(uuid.uuid4()); c.execute('INSERT INTO queue(id,phone,message,status,created_at) VALUES(?,?,?,?,?)',(q,phone,message,'pending',iso(now()))); event(c,phone,'queued',q); c.commit(); c.close(); return {'accepted':True,'queue_id':q}
def claim_next():
    expire_inactive()
    with _lock:
        c=connect(); r=c.execute("""SELECT q.*,c.opt_in,c.conversation_active FROM queue q JOIN contacts c ON c.phone=q.phone WHERE q.status='pending' ORDER BY q.created_at LIMIT 1""").fetchone()
        if not r: c.close(); return None
        if not r['opt_in'] or not r['conversation_active']:
            c.execute('UPDATE queue SET status=?,reason=? WHERE id=?',('blocked','Regras de segurança não atendidas',r['id'])); event(c,r['phone'],'blocked','Fila bloqueada'); c.commit(); c.close(); return None
        c.execute('UPDATE queue SET status=?,started_at=? WHERE id=?',('processing',iso(now()),r['id'])); c.commit(); c.close(); return dict(r)
def mark_sent(qid):
    with _lock:
        c=connect(); r=c.execute('SELECT phone FROM queue WHERE id=?',(qid,)).fetchone(); t=iso(now()); c.execute('UPDATE queue SET status=?,sent_at=? WHERE id=?',('sent',t,qid));
        if r: c.execute('UPDATE contacts SET last_outgoing_at=?,total_outgoing=total_outgoing+1,updated_at=? WHERE phone=?',(t,t,r['phone'])); event(c,r['phone'],'outgoing',qid)
        c.commit(); c.close()
def mark_failed(qid,error):
    with _lock:
        c=connect(); r=c.execute('SELECT phone FROM queue WHERE id=?',(qid,)).fetchone(); c.execute('UPDATE queue SET status=?,error=? WHERE id=?',('failed',str(error)[:1000],qid));
        if r: event(c,r['phone'],'failed',str(error)[:500])
        c.commit(); c.close()
def dashboard():
    expire_inactive()
    with _lock:
        c=connect(); count=lambda sql:c.execute(sql).fetchone()['n']; d={'contacts':count('SELECT COUNT(*) n FROM contacts'),'opted_in':count('SELECT COUNT(*) n FROM contacts WHERE opt_in=1'),'active_conversations':count('SELECT COUNT(*) n FROM contacts WHERE conversation_active=1'),'queue_pending':count("SELECT COUNT(*) n FROM queue WHERE status='pending'"),'sent':count("SELECT COUNT(*) n FROM queue WHERE status='sent'"),'failed':count("SELECT COUNT(*) n FROM queue WHERE status='failed'"),'blocked':count("SELECT COUNT(*) n FROM events WHERE event_type='blocked'"),'rules':{'active_window_hours':ACTIVE_WINDOW_HOURS,'min_delay_seconds':MIN_DELAY_SECONDS,'max_delay_seconds':MAX_DELAY_SECONDS}}; d['recent_events']=[dict(row) for row in c.execute('SELECT phone,event_type,detail,created_at FROM events ORDER BY id DESC LIMIT 30').fetchall()]; c.close(); return d
def list_queue(limit=100):
    with _lock:
        c=connect(); rows=c.execute('SELECT id,phone,message,status,reason,created_at,started_at,sent_at,error FROM queue ORDER BY created_at DESC LIMIT ?',(limit,)).fetchall(); c.close(); return [dict(x) for x in rows]
init_db()
