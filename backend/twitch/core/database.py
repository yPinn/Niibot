import asyncpg


async def setup_database_schema(connection: asyncpg.Connection) -> None:
    """Initialize database tables and triggers."""
    await connection.execute(
        """CREATE TABLE IF NOT EXISTS tokens(
            user_id TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            refresh TEXT NOT NULL
        )"""
    )

    await connection.execute(
        """CREATE TABLE IF NOT EXISTS channels(
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL UNIQUE,
            enabled BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    await connection.execute(
        """
        CREATE OR REPLACE FUNCTION notify_channel_toggle()
        RETURNS TRIGGER AS $$
        DECLARE
            payload TEXT;
        BEGIN
            IF NEW.enabled IS DISTINCT FROM OLD.enabled THEN
                payload := json_build_object(
                    'channel_id', NEW.channel_id,
                    'channel_name', NEW.channel_name,
                    'enabled', NEW.enabled
                )::text;

                PERFORM pg_notify('channel_toggle', payload);
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    await connection.execute(
        """
        DROP TRIGGER IF EXISTS channel_toggle_trigger ON channels;
        CREATE TRIGGER channel_toggle_trigger
        AFTER UPDATE ON channels
        FOR EACH ROW
        EXECUTE FUNCTION notify_channel_toggle();
        """
    )
