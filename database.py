import asyncpg
import os


class Database:
    def __init__(self):
        self.pool = None  # Database connection pool

    async def connect(self):
        """Connect to PostgreSQL database."""
        self.pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

    async def close(self):
        """Close the database connection."""
        await self.pool.close()

    async def add_user(self, user_id, username):
        """Add a user if they don’t exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, points)
                VALUES ($1, $2, 0) ON CONFLICT (user_id) DO NOTHING
            """, user_id, username)

            # Ensure progress tracking exists for the user
            await conn.execute("""
                INSERT INTO progress (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)

            # Ensure PR tracking exists for the user
            await conn.execute("""
                INSERT INTO personal_records (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)

    async def log_checkin(self, user_id, category):
        """Log a gym or food check-in."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO checkins (user_id, category)
                VALUES ($1, $2)
            """, user_id, category)

            if category == "gym":
                await conn.execute("""
                    UPDATE progress SET total_gym_checkins = total_gym_checkins + 1 WHERE user_id = $1
                """, user_id)
            elif category == "food":
                await conn.execute("""
                    UPDATE progress SET total_food_logs = total_food_logs + 1 WHERE user_id = $1
                """, user_id)

    async def update_weight(self, user_id, weight):
        """Update user's weight and track progress."""
        async with self.pool.acquire() as conn:
            previous_weight = await conn.fetchval("""
                SELECT last_logged_weight FROM progress WHERE user_id = $1
            """, user_id)

            if previous_weight:
                weight_change = weight - previous_weight
                await conn.execute("""
                    UPDATE progress SET total_weight_change = total_weight_change + $1, last_logged_weight = $2 WHERE user_id = $3
                """, weight_change, weight, user_id)
            else:
                await conn.execute("""
                    UPDATE progress SET last_logged_weight = $1 WHERE user_id = $2
                """, weight, user_id)

    async def update_pr(self, user_id, lift, value):
        """Update the user's personal record (PR) for deadlift, bench, or squat."""
        async with self.pool.acquire() as conn:
            if lift in ["deadlift", "bench", "squat"]:
                await conn.execute(f"""
                    UPDATE personal_records SET {lift} = $1 WHERE user_id = $2
                """, value, user_id)

    async def get_progress(self, user_id):
        """Get a user's total check-ins, food logs, and weight progress."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT total_gym_checkins, total_food_logs, total_weight_change FROM progress WHERE user_id = $1
            """, user_id)

    async def get_personal_records(self, user_id):
        """Retrieve a user's personal records (PRs)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT deadlift, bench, squat FROM personal_records WHERE user_id = $1
            """, user_id)


db = Database()