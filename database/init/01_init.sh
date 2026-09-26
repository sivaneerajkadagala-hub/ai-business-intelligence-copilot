#!/bin/bash
# Initializes schemas and roles for AI BI Copilot.
# Runs once on first postgres container startup (fresh volume).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Schema holding imported dataset tables (data.ds_*)
    CREATE SCHEMA IF NOT EXISTS data;

    -- Read-only role for AI-generated / analytics queries.
    -- It can only SELECT from the data schema — never write, never touch public.
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_reader') THEN
            CREATE ROLE bi_reader LOGIN PASSWORD '${BI_READER_PASSWORD:-bi_reader_dev}';
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO bi_reader;
    GRANT USAGE ON SCHEMA data TO bi_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA data TO bi_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA data GRANT SELECT ON TABLES TO bi_reader;
EOSQL
