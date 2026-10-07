"""SQLite storage for users and recommendation history."""
import hashlib, hmac, json, os, sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "pocketsmart.db")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            inputs TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def create_user(username, email, password):
    salt = os.urandom(16).hex()
    try:
        with conn() as c:
            c.execute("INSERT INTO users(username,email,salt,password_hash) VALUES(?,?,?,?)",
                      (username, email, salt, _hash(password, salt)))
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username, password):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row and hmac.compare_digest(row["password_hash"], _hash(password, row["salt"])):
        return dict(row)
    return None


def get_user(username):
    with conn() as c:
        row = c.execute("SELECT id,username,email FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def save_history(user_id, category, inputs, result):
    with conn() as c:
        cur = c.execute("INSERT INTO history(user_id,category,inputs,result) VALUES(?,?,?,?)",
                        (user_id, category, json.dumps(inputs), json.dumps(result)))
        return cur.lastrowid


def list_history(user_id, limit=50):
    with conn() as c:
        rows = c.execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    return [_row(r) for r in rows]


def get_history_item(user_id, item_id):
    with conn() as c:
        r = c.execute("SELECT * FROM history WHERE id=? AND user_id=?", (item_id, user_id)).fetchone()
    return _row(r) if r else None


def _row(r):
    d = dict(r)
    d["inputs"], d["result"] = json.loads(d["inputs"]), json.loads(d["result"])
    return d
