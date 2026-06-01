"""
Migration: Add denormalized search columns to job_logs table.

Adds indexed columns (session_id, church_name, member_name, user_message, agent_response)
extracted from request_data/response_data JSON to enable fast indexed searches
instead of expensive CAST(JSON→text) + ILIKE full table scans.

Also creates pg_trgm GIN indexes for ILIKE pattern matching on text fields.
Finally, backfills all existing rows using SQL JSON extraction.
"""
import asyncio
from app.database import engine

async def run():
    async with engine.begin() as conn:
        # ── Step 1: Add columns if they don't exist ──
        columns = [
            ("session_id", "VARCHAR(255)"),
            ("church_name", "VARCHAR(255)"),
            ("member_name", "VARCHAR(500)"),
            ("user_message", "TEXT"),
            ("agent_response", "TEXT"),
        ]

        for col_name, col_type in columns:
            await conn.execute(
                __import__("sqlalchemy").text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'job_logs' AND column_name = '{col_name}'
                        ) THEN
                            ALTER TABLE job_logs ADD COLUMN {col_name} {col_type};
                        END IF;
                    END $$;
                """)
            )
        print("✅ Columns added (or already existed)")

        # ── Step 2: Create B-tree indexes on exact-match / prefix-match columns ──
        btree_indexes = [
            ("ix_job_logs_session_id", "session_id"),
            ("ix_job_logs_church_name", "church_name"),
            ("ix_job_logs_member_name", "member_name"),
        ]
        for idx_name, col_name in btree_indexes:
            await conn.execute(
                __import__("sqlalchemy").text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name} ON job_logs ({col_name});
                """)
            )
        print("✅ B-tree indexes created")

        # ── Step 3: Enable pg_trgm extension and create GIN trigram indexes ──
        # These indexes make ILIKE '%pattern%' queries fast
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        )

        gin_indexes = [
            ("ix_job_logs_user_message_trgm", "user_message"),
            ("ix_job_logs_agent_response_trgm", "agent_response"),
        ]
        for idx_name, col_name in gin_indexes:
            await conn.execute(
                __import__("sqlalchemy").text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name}
                    ON job_logs USING gin ({col_name} gin_trgm_ops);
                """)
            )
        print("✅ GIN trigram indexes created (pg_trgm)")

        # ── Step 4: Create composite index for common filter combo (status + created_at) ──
        await conn.execute(
            __import__("sqlalchemy").text("""
                CREATE INDEX IF NOT EXISTS ix_job_logs_status_created
                ON job_logs (status, created_at DESC);
            """)
        )
        print("✅ Composite index (status, created_at) created")

        # ── Step 5: Backfill existing rows ──
        # Extract fields from JSON using PostgreSQL JSON operators (fast, no Python loop)
        result = await conn.execute(
            __import__("sqlalchemy").text("""
                UPDATE job_logs SET
                    session_id = COALESCE(session_id, request_data->>'session_id'),
                    church_name = COALESCE(church_name, request_data->'church'->>'church_name'),
                    member_name = COALESCE(member_name,
                        COALESCE(
                            request_data->'member'->>'fullname',
                            request_data->'context_data'->>'name',
                            request_data->>'name'
                        )
                    ),
                    user_message = COALESCE(user_message, request_data->>'message'),
                    agent_response = COALESCE(agent_response,
                        COALESCE(
                            response_data->>'result',
                            response_data->>'response',
                            response_data->>'output',
                            response_data->>'resposta'
                        )
                    )
                WHERE session_id IS NULL
                   OR church_name IS NULL
                   OR member_name IS NULL
                   OR user_message IS NULL
                   OR agent_response IS NULL;
            """)
        )
        print(f"✅ Backfilled {result.rowcount} existing rows")

    await engine.dispose()
    print("\n🎉 Migration complete! Search queries will now use indexed columns.")

if __name__ == "__main__":
    asyncio.run(run())
