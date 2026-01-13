# Database Migrations

This directory contains SQL migration scripts for the Niibot database schema.

## Running Migrations

To apply migrations, connect to your PostgreSQL database and run the SQL files in order:

### Using psql command line:

```bash
# Set your database URL
export DATABASE_URL="postgresql://user:password@localhost:5432/niibot"

# Run migration
psql $DATABASE_URL -f 001_add_game_info.sql
```

### Using Python script:

```python
import asyncio
import asyncpg
from api.core.config import get_settings

async def run_migration():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)

    try:
        with open('001_add_game_info.sql', 'r') as f:
            migration_sql = f.read()

        await conn.execute(migration_sql)
        print("Migration completed successfully!")
    finally:
        await conn.close()

asyncio.run(run_migration())
```

## Migration History

### 001_add_game_info.sql
- Adds `game_id` column to `stream_sessions` table
- Creates index on `game_id` for faster game lookups
- Game box art URLs are generated dynamically in frontend using format: `https://static-cdn.jtvnw.net/ttv-boxart/{game_id}-{width}x{height}.jpg`
- This approach avoids storing potentially stale URLs and always shows the latest game cover art from Twitch CDN
