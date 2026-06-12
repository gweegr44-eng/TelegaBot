import sqlite3

class Storage:
    def __init__(self, db_path='database.db'):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def upsert_user(self, user_id: int, **kwargs):
        allowed_fields = {'calendar_id', 'reminder_minutes', 'access_token',
                          'refresh_token', 'token_expiry', 'credentials_json',
                          'city', 'country'}
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
        self.conn.execute(sql, [user_id] + values)
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