-- Три входа в базу (TD-DB-01, ADR-0054). Запускает суперпользователь: scripts/db/roles.sh.
-- Повторный запуск безопасен: меняет пароли и заново раздаёт права (например, после миграции).
--   muallim_owner  — владелец таблиц: только он меняет схему (alembic, MIGRATION_DATABASE_URL);
--   muallim_app    — бот и muallim-research: читать и писать строки, схему не трогать;
--   muallim_reader — DBeaver и отчёты: только чтение, без Telegram ID.
-- Пароли — переменные psql (\set owner_password '…' и т. д.; roles.sh передаёт их через stdin).

DO $$
DECLARE role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['muallim_owner', 'muallim_app', 'muallim_reader'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('CREATE ROLE %I LOGIN', role_name);
        END IF;
        EXECUTE format(
            'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
            role_name
        );
    END LOOP;
END $$;

ALTER ROLE muallim_owner PASSWORD :'owner_password';
ALTER ROLE muallim_app PASSWORD :'app_password';
ALTER ROLE muallim_reader PASSWORD :'reader_password';
-- Просмотр не может ничего изменить даже по ошибке.
ALTER ROLE muallim_reader SET default_transaction_read_only = on;

-- В эту базу входят только три роли (и суперпользователь для копий и восстановления).
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO muallim_owner, muallim_app, muallim_reader',
        current_database()
    );
    EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO muallim_owner', current_database());
END $$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO muallim_owner;
GRANT USAGE ON SCHEMA public TO muallim_app, muallim_reader;

-- Таблицы, представления и последовательности, созданные раньше суперпользователем, — владельцу.
DO $$
DECLARE obj record;
BEGIN
    FOR obj IN
        SELECT c.relname, c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'S', 'p')
            -- последовательность колонки (serial/identity) переходит вместе со своей таблицей
            AND NOT EXISTS (
                SELECT FROM pg_depend d
                WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                    AND d.deptype IN ('a', 'i')
            )
    LOOP
        IF obj.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE public.%I OWNER TO muallim_owner', obj.relname);
        ELSIF obj.relkind IN ('v', 'm') THEN
            EXECUTE format('ALTER VIEW public.%I OWNER TO muallim_owner', obj.relname);
        ELSE
            EXECUTE format('ALTER TABLE public.%I OWNER TO muallim_owner', obj.relname);
        END IF;
    END LOOP;
END $$;

-- Бот: строки — да (DELETE нужен для «Удалить мои данные» и отзыва согласия); схема, TRUNCATE — нет.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO muallim_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO muallim_app;
-- Версию схемы меняют только миграции (владелец); бот её лишь читает.
DO $$
BEGIN
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM muallim_app;
    END IF;
END $$;

-- Просмотр: всё для чтения, кроме Telegram ID и кодов приглашений.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO muallim_reader;
DO $$
DECLARE col record;
BEGIN
    -- Таблица с Telegram ID: право на чтение — по колонкам, кроме самого ID.
    FOR col IN
        SELECT DISTINCT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name LIKE '%telegram%'
    LOOP
        EXECUTE format('REVOKE SELECT ON public.%I FROM muallim_reader', col.table_name);
        EXECUTE (
            SELECT format(
                'GRANT SELECT (%s) ON public.%I TO muallim_reader',
                string_agg(quote_ident(column_name), ', '), col.table_name
            )
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = col.table_name
                AND column_name NOT LIKE '%telegram%'
        );
    END LOOP;
    IF to_regclass('public.annotator_invites') IS NOT NULL THEN
        REVOKE SELECT ON public.annotator_invites FROM muallim_reader;
    END IF;
END $$;

-- Таблицы, которые миграции создадут потом (владелец — muallim_owner), получат те же права.
-- Новая колонка с Telegram ID откроется просмотру — после такой миграции запустите roles.sh снова
-- (тест tests/integration/test_postgres_roles.py проверяет, что Telegram ID скрыт).
ALTER DEFAULT PRIVILEGES FOR ROLE muallim_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO muallim_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muallim_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO muallim_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muallim_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO muallim_reader;
