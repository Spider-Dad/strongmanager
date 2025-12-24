"""
Скрипт инициализации PostgreSQL базы данных

Использование:
    python db/init_database.py

Что делает:
1. Проверяет подключение к PostgreSQL
2. Создает все таблицы из schema.sql
3. Создает индексы и представления
4. Выводит статус инициализации

ВАЖНО:
- Запускать только один раз при первоначальной настройке
- Справочные данные (mentors, students, trainings, lessons, mapping)
  заполняются вручную через DBeaver
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь для импорта
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import asyncpg
from dotenv import load_dotenv
import os

# Загружаем переменные окружения из .env в корне проекта
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"[OK] Загружен .env из {env_path}")
else:
    print(f"[!] Файл .env не найден: {env_path}")
    print(f"    Пытаемся загрузить из текущей директории...")
    load_dotenv()  # Fallback на текущую директорию


async def check_connection(conn):
    """Проверка подключения к БД"""
    try:
        result = await conn.fetchval('SELECT version()')
        print(f"[OK] Подключение установлено")
        print(f"  PostgreSQL версия: {result}")
        return True
    except Exception as e:
        print(f"[ERROR] Ошибка подключения: {e}")
        return False


async def create_schema(conn):
    """Создание схемы БД из schema.sql"""
    try:
        schema_path = Path(__file__).parent / "schema.sql"

        if not schema_path.exists():
            print(f"[ERROR] Файл schema.sql не найден: {schema_path}")
            return False

        print(f"\n[INFO] Чтение schema.sql из {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        print(f"[OK] Файл schema.sql прочитан ({len(schema_sql)} символов)")
        print(f"\n[INFO] Выполнение SQL скрипта...")

        # Выполняем весь SQL скрипт
        await conn.execute(schema_sql)

        print(f"[OK] Схема базы данных создана успешно")
        return True

    except Exception as e:
        print(f"[ERROR] Ошибка при создании схемы: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_tables(conn):
    """Проверка созданных таблиц"""
    try:
        # Получаем список всех таблиц
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        print(f"\n[INFO] Созданные таблицы ({len(tables)}):")
        for table in tables:
            # Получаем количество столбцов
            columns = await conn.fetchval("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = $1
            """, table['table_name'])

            print(f"  - {table['table_name']} ({columns} столбцов)")

        return True

    except Exception as e:
        print(f"[ERROR] Ошибка при проверке таблиц: {e}")
        return False


async def check_views(conn):
    """Проверка созданных представлений"""
    try:
        views = await conn.fetch("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        print(f"\n[INFO] Созданные представления ({len(views)}):")
        for view in views:
            print(f"  - {view['table_name']}")

        return True

    except Exception as e:
        print(f"[ERROR] Ошибка при проверке представлений: {e}")
        return False


async def check_indexes(conn):
    """Проверка созданных индексов"""
    try:
        indexes = await conn.fetch("""
            SELECT
                schemaname,
                tablename,
                indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
        """)

        print(f"\n[INFO] Созданные индексы ({len(indexes)}):")

        current_table = None
        for idx in indexes:
            if current_table != idx['tablename']:
                current_table = idx['tablename']
                print(f"\n  Таблица: {current_table}")
            print(f"    - {idx['indexname']}")

        return True

    except Exception as e:
        print(f"[ERROR] Ошибка при проверке индексов: {e}")
        return False


async def main():
    """Основная функция инициализации"""
    print("="*70)
    print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ PostgreSQL")
    print("="*70)

    # Получаем параметры подключения из переменных окружения
    env = os.getenv("SERVER_ENV", "dev")

    if env == "prod":
        host = os.getenv("POSTGRES_HOST_INTERNAL", "amvera-spiderdad-cnpg-getcoursebd-rw")
    else:
        host = os.getenv("POSTGRES_HOST_EXTERNAL", "getcoursebd-spiderdad.db-msk0.amvera.tech")

    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgresql")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "GetCourseBD")

    print(f"\n[INFO] Параметры подключения:")
    print(f"  Окружение: {env}")
    print(f"  Хост: {host}")
    print(f"  Порт: {port}")
    print(f"  БД: {database}")
    print(f"  Пользователь: {user}")

    if not password:
        print(f"\n[!] ВНИМАНИЕ: Пароль не указан в переменных окружения!")
        print(f"  Установите POSTGRES_PASSWORD в .env файле")
        return

    print(f"\n[INFO] Подключение к PostgreSQL...")

    try:
        # Подключение к БД с увеличенным таймаутом
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            timeout=60  # Увеличиваем таймаут до 60 секунд
        )

        # Проверка подключения
        if not await check_connection(conn):
            return

        # Создание схемы
        if not await create_schema(conn):
            return

        # Проверка таблиц
        await check_tables(conn)

        # Проверка представлений
        await check_views(conn)

        # Проверка индексов
        await check_indexes(conn)

        # Закрываем соединение
        await conn.close()

        print("\n" + "="*70)
        print("[SUCCESS] ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("="*70)
        print("\n[INFO] Следующие шаги:")
        print("  1. Заполните справочные таблицы через DBeaver:")
        print("     - mentors (наставники)")
        print("     - students (студенты)")
        print("     - trainings (тренинги)")
        print("     - lessons (уроки)")
        print("     - mapping (связи студент-ментор)")
        print("  2. Проверьте n8n workflow для записи в webhook_events")
        print("  3. Запустите бота для обработки вебхуков")
        print()

    except asyncpg.exceptions.InvalidPasswordError:
        print(f"\n[ERROR] Ошибка: Неверный пароль")
        print(f"  Проверьте POSTGRES_PASSWORD в .env файле")
    except asyncpg.exceptions.InvalidCatalogNameError:
        print(f"\n[ERROR] Ошибка: База данных '{database}' не существует")
        print(f"  Создайте базу данных на сервере PostgreSQL")
    except Exception as e:
        print(f"\n[ERROR] Ошибка при инициализации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Для Windows используем SelectorEventLoopPolicy
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
