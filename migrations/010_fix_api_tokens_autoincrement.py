"""
Fix API tokens and usage tables autoincrement
Adds SERIAL autoincrement to id columns in api_tokens and api_usage tables
"""

def upgrade(migration_system):
    """Fix autoincrement for API tokens tables"""

    # Check if we're using PostgreSQL
    engine_name = migration_system.engine.dialect.name

    if engine_name == 'postgresql':
        # PostgreSQL: Create sequences and set them as default
        fix_api_tokens_seq = """
        -- Create sequence for api_tokens if not exists
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_sequences WHERE schemaname = 'public' AND sequencename = 'api_tokens_id_seq') THEN
                CREATE SEQUENCE api_tokens_id_seq;

                -- Set the sequence to start from the next available ID
                PERFORM setval('api_tokens_id_seq', COALESCE((SELECT MAX(id) FROM api_tokens), 0) + 1, false);

                -- Set the sequence as default for id column
                ALTER TABLE api_tokens ALTER COLUMN id SET DEFAULT nextval('api_tokens_id_seq');

                -- Set the sequence owner
                ALTER SEQUENCE api_tokens_id_seq OWNED BY api_tokens.id;
            END IF;
        END $$;
        """

        fix_api_usage_seq = """
        -- Create sequence for api_usage if not exists
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_sequences WHERE schemaname = 'public' AND sequencename = 'api_usage_id_seq') THEN
                CREATE SEQUENCE api_usage_id_seq;

                -- Set the sequence to start from the next available ID
                PERFORM setval('api_usage_id_seq', COALESCE((SELECT MAX(id) FROM api_usage), 0) + 1, false);

                -- Set the sequence as default for id column
                ALTER TABLE api_usage ALTER COLUMN id SET DEFAULT nextval('api_usage_id_seq');

                -- Set the sequence owner
                ALTER SEQUENCE api_usage_id_seq OWNED BY api_usage.id;
            END IF;
        END $$;
        """

        with migration_system.engine.connect() as conn:
            from sqlalchemy import text

            try:
                conn.execute(text(fix_api_tokens_seq))
                print("Fixed api_tokens autoincrement (PostgreSQL)")

                conn.execute(text(fix_api_usage_seq))
                print("Fixed api_usage autoincrement (PostgreSQL)")

                conn.commit()
                print("API tokens autoincrement fixed successfully")

            except Exception as e:
                print(f"Error fixing API tokens autoincrement: {e}")
                conn.rollback()
                raise

    elif engine_name == 'sqlite':
        # SQLite: Already has autoincrement by default for INTEGER PRIMARY KEY
        print("SQLite detected - autoincrement already works correctly")

    else:
        print(f"Unknown database engine: {engine_name}")

def downgrade(migration_system):
    """Revert autoincrement changes"""

    engine_name = migration_system.engine.dialect.name

    if engine_name == 'postgresql':
        with migration_system.engine.connect() as conn:
            from sqlalchemy import text

            try:
                # Remove sequences
                conn.execute(text("DROP SEQUENCE IF EXISTS api_tokens_id_seq CASCADE"))
                print("Removed api_tokens_id_seq")

                conn.execute(text("DROP SEQUENCE IF EXISTS api_usage_id_seq CASCADE"))
                print("Removed api_usage_id_seq")

                conn.commit()
                print("API tokens autoincrement reverted successfully")

            except Exception as e:
                print(f"Error reverting API tokens autoincrement: {e}")
                conn.rollback()
