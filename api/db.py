import os
from dotenv import load_dotenv

try:
    import pymysql
except ModuleNotFoundError:
    pymysql = None

load_dotenv()

def get_db_connection():
    if pymysql is None:
        raise RuntimeError("PyMySQL is not installed")

    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
