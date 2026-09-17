from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROLES = ('legal', 'design', 'finance', 'strategy')


def identify_owner(updates: list[dict], username: str) -> int:
    """Return an ID only from an incoming private /start, without exposing messages."""
    expected=username.lstrip('@').casefold()
    matches=set()
    for update in updates:
        message=update.get('message',{})
        sender=message.get('from',{})
        if (message.get('chat',{}).get('type')=='private'
                and message.get('text','').split(' ',1)[0]=='/start'
                and not sender.get('is_bot')
                and sender.get('username','').casefold()==expected
                and isinstance(sender.get('id'),int)):
            matches.add(sender['id'])
    if len(matches)!=1:
        raise ValueError('Нужен единственный свежий /start от указанного аккаунта в личном чате бота. Отправьте /start и повторите проверку.')
    return matches.pop()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def split_message(text: str, limit: int = 3500) -> list[str]:
    chunks, buf, units = [], [], 0
    for char in text:
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > limit:
            chunks.append(''.join(buf)); buf, units = [], 0
        buf.append(char); units += size
    if buf:
        chunks.append(''.join(buf))
    return chunks or ['(пустой результат)']


def load_env_file(path: Path) -> None:
    """Load a private .env without shell evaluation or variable expansion."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Неверная строка .env')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


@dataclass
class Settings:
    owner_ids: frozenset[int] = field(default_factory=frozenset)
    tokens: dict[str, str] = field(default_factory=dict, repr=False)
    api_key: str = field(default='', repr=False)
    model: str = ''
    daily_calls: int = 40
    max_attempts: int = 3
    channel: str = ''
    root: Path = field(default_factory=Path.cwd)

    @classmethod
    def from_env(cls, env=None, root=None):
        env = os.environ if env is None else env
        ids = frozenset(int(x.strip()) for x in env.get('SKIF_OWNER_IDS', '').split(',') if x.strip())
        daily, attempts = int(env.get('SKIF_DAILY_AI_CALLS', '40')), int(env.get('SKIF_DESIGN_ATTEMPTS', '3'))
        if any(i <= 0 for i in ids) or not 1 <= daily <= 500 or not 1 <= attempts <= 3:
            raise ValueError('Проверьте ID владельцев и лимиты в .env')
        return cls(ids, {r: env.get('TELEGRAM_' + r.upper() + '_TOKEN', '') for r in ROLES},
                   env.get('OPENAI_API_KEY', ''), env.get('OPENAI_MODEL', ''), daily, attempts,
                   env.get('SKIF_BLOG_CHANNEL', ''), Path(root or Path.cwd()).resolve())

    def authorized(self, user_id, chat_type):
        return user_id in self.owner_ids and chat_type == 'private'

    def missing(self):
        names = [f'TELEGRAM_{r.upper()}_TOKEN' for r in ROLES if not self.tokens.get(r)]
        if not self.owner_ids: names.append('SKIF_OWNER_IDS')
        if not self.api_key: names.append('OPENAI_API_KEY')
        if not self.model: names.append('OPENAI_MODEL')
        return names


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, owner INTEGER, role TEXT, kind TEXT, brief TEXT,
          status TEXT, result TEXT DEFAULT '', files TEXT DEFAULT '[]', created TEXT,
          publication TEXT DEFAULT 'draft', message_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS updates (role TEXT, update_id INTEGER, PRIMARY KEY(role,update_id));
        CREATE TABLE IF NOT EXISTS budgets (day TEXT PRIMARY KEY, calls INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, owner INTEGER, name TEXT,
          contact TEXT, plot TEXT, next_step TEXT, created TEXT);
        ''')
        self.db.commit()

    def close(self): self.db.close()

    def create_task(self, owner, role, kind, brief):
        if role not in ROLES or len(brief) > 20000:
            raise ValueError('Неверная роль или слишком длинное задание')
        ident = uuid.uuid4().hex[:12]
        with self.lock, self.db:
            self.db.execute('INSERT INTO tasks(id,owner,role,kind,brief,status,created) VALUES(?,?,?,?,?,?,?)',
                            (ident, owner, role, kind, brief, 'working', now()))
        return ident

    def finish(self, ident, status, result, files):
        with self.lock, self.db:
            self.db.execute('UPDATE tasks SET status=?,result=?,files=? WHERE id=?',
                            (status, result, json.dumps([str(p) for p in files]), ident))

    def get_task(self, ident, owner):
        with self.lock:
            row = self.db.execute('SELECT * FROM tasks WHERE id=?', (ident,)).fetchone()
        if not row or row['owner'] != owner:
            raise PermissionError('Задача недоступна этому пользователю')
        data = dict(row); data['files'] = json.loads(data['files'])
        return data

    def list_tasks(self, owner):
        with self.lock:
            return [dict(x) for x in self.db.execute('SELECT id,role,kind,status,created FROM tasks WHERE owner=? ORDER BY created DESC,rowid DESC LIMIT 15', (owner,))]

    def publication_digest(self, ident, owner):
        item = self.get_task(ident, owner)
        if item['kind'] != 'blog' or item['role'] != 'strategy' or item['status'] != 'needs_owner_review':
            raise ValueError('Публиковать можно только готовый черновик блога')
        if item['publication'] != 'draft':
            raise ValueError('Публикация уже отправлена либо требует ручной проверки')
        return hashlib.sha256(item['result'].encode()).hexdigest()[:12]

    def claim_publication(self, ident, owner, digest):
        with self.lock, self.db:
            expected = self.publication_digest(ident, owner)
            if expected != digest:
                raise ValueError('Подтверждение не соответствует показанному тексту')
            item = self.get_task(ident, owner)
            if len(item['result'].encode('utf-16-le')) // 2 > 3500:
                raise ValueError('Сократите публикацию до 3500 символов перед отправкой')
            self.db.execute('UPDATE tasks SET publication=? WHERE id=?', ('sending', ident))
            return item['result']

    def publication_result(self, ident, state, message_id):
        if state not in ('published', 'unknown'): raise ValueError('Неверное состояние')
        with self.lock, self.db:
            self.db.execute('UPDATE tasks SET publication=?,message_id=? WHERE id=? AND publication=?',
                            (state, str(message_id), ident, 'sending'))

    def claim_update(self, role, ident):
        with self.lock, self.db:
            cursor = self.db.execute('INSERT OR IGNORE INTO updates VALUES(?,?)', (role, ident))
            return cursor.rowcount == 1

    def offset(self, role):
        with self.lock:
            row = self.db.execute('SELECT MAX(update_id) FROM updates WHERE role=?', (role,)).fetchone()
        return 0 if row[0] is None else row[0] + 1

    def reserve_call(self, limit, day=None):
        day = day or datetime.now(timezone.utc).date().isoformat()
        with self.lock, self.db:
            current = self.db.execute('SELECT calls FROM budgets WHERE day=?', (day,)).fetchone()
            if current and current[0] >= limit:
                raise ValueError('Дневной лимит обращений к ИИ исчерпан. Расчёты продолжают работать.')
            self.db.execute('INSERT INTO budgets VALUES(?,1) ON CONFLICT(day) DO UPDATE SET calls=calls+1', (day,))

    def add_lead(self, owner, name, contact, plot, next_step):
        if not name or not contact or any(len(x) > 300 for x in (name, contact, plot, next_step)):
            raise ValueError('Нужны имя и контакт; поля до 300 символов')
        ident = uuid.uuid4().hex[:12]
        with self.lock, self.db:
            self.db.execute('INSERT INTO leads VALUES(?,?,?,?,?,?,?)', (ident,owner,name,contact,plot,next_step,now()))
        return ident

    def leads(self, owner):
        with self.lock:
            return [dict(x) for x in self.db.execute('SELECT * FROM leads WHERE owner=? ORDER BY created DESC LIMIT 30', (owner,))]

    def recover(self):
        with self.lock, self.db:
            self.db.execute("UPDATE tasks SET publication='unknown' WHERE publication='sending'")
            self.db.execute("UPDATE tasks SET status='interrupted', result='Работа прервана перезапуском. Создайте новое задание.' WHERE status='working'")
