import os
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text

# --- Настройки ---
# Путь к SQLite (внутри контейнера Bothost)
SQLITE_DB_PATH = "/app/data/rsreu_bot.db"

# Строка подключения к PostgreSQL (ты возьмешь её из карточки базы Bothost)
# Она должна быть в переменных окружения бота с именем DATABASE_URL
POSTGRES_URL = os.environ.get("DATABASE_URL")

def sync_tables():
    """
    Переносит данные из всех таблиц SQLite в PostgreSQL.
    Использует pandas для чтения/записи.
    """
    if not POSTGRES_URL:
        print("❌ Ошибка: переменная окружения DATABASE_URL не найдена!")
        return

    print("🔄 Начало синхронизации...")

    # Подключаемся к SQLite
    src_conn = sqlite3.connect(SQLITE_DB_PATH)
    
    # Создаем движок для PostgreSQL
    dst_engine = create_engine(POSTGRES_URL)

    # Список таблиц для синхронизации (все, кроме системных)
    tables_to_sync = [
        "users",
        "schedule",
        "homework",
        "homework_status",
        "debts",
        "attendance"
    ]

    for table_name in tables_to_sync:
        try:
            # Читаем данные из SQLite
            df = pd.read_sql(f'SELECT * FROM "{table_name}"', src_conn)
            
            # Заменяем пустые строки на None (PostgreSQL не любит пустые строки в некоторых типах)
            df = df.replace('', None)

            # Записываем в PostgreSQL
            # if_exists='replace' перезапишет таблицу целиком.
            # Для периодического обновления лучше использовать 'append' с предварительной очисткой,
            # но 'replace' надежнее для полного копирования.
            # ВАЖНО: Это удалит все данные в PostgreSQL и зальет заново. 
            # Если нужно сохранять изменения, сделанные прямо в PostgreSQL, логику надо менять.
            df.to_sql(table_name, dst_engine, if_exists='replace', index=False)
            
            print(f"✅ Таблица {table_name} синхронизирована. Строк: {len(df)}")

        except Exception as e:
            print(f"❌ Ошибка при синхронизации таблицы {table_name}: {e}")

    src_conn.close()
    print("🎉 Синхронизация завершена!")

if __name__ == "__main__":
    sync_tables()
