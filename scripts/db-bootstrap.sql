\set ON_ERROR_STOP on

\if :{?catforge_db_name}
\else
\set catforge_db_name catforge_dev
\endif

\if :{?catforge_app_user}
\else
\set catforge_app_user catforge_app
\endif

\if :{?catforge_app_password}
\else
\echo 'catforge_app_password is required'
\quit 2
\endif

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'catforge_app_user', :'catforge_app_password')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'catforge_app_user'
)
\gexec

ALTER ROLE :"catforge_app_user" WITH LOGIN PASSWORD :'catforge_app_password';

SELECT format('CREATE DATABASE %I OWNER %I ENCODING %L', :'catforge_db_name', :'catforge_app_user', 'UTF8')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = :'catforge_db_name'
)
\gexec

\connect :catforge_db_name

ALTER DATABASE :"catforge_db_name" OWNER TO :"catforge_app_user";
CREATE SCHEMA IF NOT EXISTS public;
ALTER SCHEMA public OWNER TO :"catforge_app_user";
GRANT CONNECT, TEMPORARY ON DATABASE :"catforge_db_name" TO :"catforge_app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"catforge_app_user";
