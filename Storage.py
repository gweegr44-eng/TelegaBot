import sqlite3
import json
from datetime import datetime

class Storage:
    def __init__(self, db_path='database.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self):
        cur = self.conn.cursor()
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                calendar_id TEXT DEFAULT 'primary',
                reminder_minutes INTEGER DEFAULT 30,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry TEXT,
                credentials_json TEXT,
                city TEXT,
                country TEXT,
                muted_events TEXT
            );

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id TEXT,
                end_time TEXT,
                title TEXT,
                link TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );

            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
        ''')
        self.conn.commit()

    def upsert_user(self, user_id: int, **kwargs):
        allowed_fields = {'calendar_id', 'reminder_minutes', 'access_token',
                          'refresh_token', 'token_expiry', 'credentials_json',
                          'city', 'country', 'muted_events'}
        data = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not data:
            return
        columns = list(data.keys())
        values = list(data.values())
        set_clause = ', '.join(f"{col} = ?" for col in columns)
        placeholders = ', '.join('?' for _ in columns)
        sql = f'''
            INSERT INTO users (user_id, {', '.join(columns)})
            VALUES (?, {placeholders})
            ON CONFLICT(user_id) DO UPDATE SET {set_clause}
        '''
        self.conn.execute(sql, [user_id] + values + values)
        self.conn.commit()

    def get_user(self, user_id: int):
        row = self.conn.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_users_with_credentials(self):
        rows = self.conn.execute(
            'SELECT * FROM users WHERE credentials_json IS NOT NULL'
        ).fetchall()
        return [dict(r) for r in rows]

    def add_history(self, user_id: int, event_id: str, end_time: str,
                    title: str, link: str):
        self.conn.execute(
            '''INSERT INTO history (user_id, event_id, end_time, title, link)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, event_id, end_time, title, link)
        )
        self.conn.commit()
        self.conn.execute('''
            DELETE FROM history
            WHERE id NOT IN (
                SELECT id FROM history
                WHERE user_id = ?
                ORDER BY end_time DESC
                LIMIT 10
            ) AND user_id = ?
        ''', (user_id, user_id))
        self.conn.commit()

    def get_last_history(self, user_id: int, limit=10):
        rows = self.conn.execute(
            '''SELECT end_time, title, link
               FROM history
               WHERE user_id = ?
               ORDER BY end_time DESC
               LIMIT ?''',
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def is_event_muted(self, user_id: int, event_id: str) -> bool:
        user = self.get_user(user_id)
        if not user or not user.get('muted_events'):
            return False
        try:
            muted = json.loads(user['muted_events'])
        except:
            return False
        return event_id in muted

    def toggle_mute_event(self, user_id: int, event_id: str, mute: bool):
        user = self.get_user(user_id)
        muted = []
        if user and user.get('muted_events'):
            try:
                muted = json.loads(user['muted_events'])
            except:
                muted = []
        if mute:
            if event_id not in muted:
                muted.append(event_id)
        else:
            if event_id in muted:
                muted.remove(event_id)
        self.upsert_user(user_id, muted_events=json.dumps(muted))

    def add_user_log(self, user_id: int, text: str):
        ts = datetime.utcnow().isoformat()
        self.conn.execute(
            'INSERT INTO user_logs (user_id, text, timestamp) VALUES (?, ?, ?)',
            (user_id, text, ts)
        )
        self.conn.commit()

    def get_user_logs(self, user_id: int, limit=20):
        rows = self.conn.execute(
            '''SELECT text, timestamp FROM user_logs
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT ?''',
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_users_list(self):
        rows = self.conn.execute(
            'SELECT user_id, city, reminder_minutes FROM users'
        ).fetchall()
        return [dict(r) for r in rows]