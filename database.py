import asyncpg
import os

class Database:
    def __init__(self):
        self.pool = None  # Database connection pool

    async def connect(self):
        """Connect to PostgreSQL database and confirm connection."""
        try:
            self.pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))
            print("✅ Database connected successfully!")  # Log success
        except Exception as e:
            print(f"❌ Database connection failed: {e}")  # Log failure

    async def close(self):
        """Close the database connection."""
        if self.pool:
            await self.pool.close()
            print("🔴 Database connection closed.")

    async def add_user(self, user_id, username):
        """Add user to the database if they don’t exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, points)
                VALUES ($1, $2, 0) ON CONFLICT (user_id) DO NOTHING
            """, user_id, username)

    async def log_checkin(self, user_id, category):
        """Log a gym or food check-in and update the progress table."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO checkins (user_id, category)
                VALUES ($1, $2)
            """, user_id, category)

            # Update progress tracking
            if category == "gym":
                await conn.execute("""
                    UPDATE progress SET total_gym_checkins = total_gym_checkins + 1 WHERE user_id = $1
                """, user_id)
            elif category == "food":
                await conn.execute("""
                    UPDATE progress SET total_food_logs = total_food_logs + 1 WHERE user_id = $1
                """, user_id)

    async def get_progress(self, user_id):
        """Retrieve user progress (total check-ins, food logs, weight change)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT total_gym_checkins, total_food_logs, total_weight_change
                FROM progress WHERE user_id = $1
            """, user_id)

    async def update_pr(self, user_id, lift, value):
        """Update the user's personal record (PR) for deadlift, bench, or squat."""
        async with self.pool.acquire() as conn:
            if lift in ["deadlift", "bench", "squat"]:
                await conn.execute(f"""
                    UPDATE personal_records SET {lift} = $1 WHERE user_id = $2
                """, value, user_id)

    async def get_personal_records(self, user_id):
        """Retrieve a user's personal records (PRs)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT deadlift, bench, squat FROM personal_records WHERE user_id = $1
            """, user_id)

    async def get_leaderboard(self):
        """Retrieve the top 10 users by points."""
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT username, points FROM users ORDER BY points DESC LIMIT 10
            """)

db = Database()