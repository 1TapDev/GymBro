import asyncpg
import os
from datetime import datetime, timedelta

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

    async def check_cooldown(self, user_id, category):
        """Check if a user is on cooldown for a specific check-in category."""
        async with self.pool.acquire() as conn:
            try:
                last_checkin = await conn.fetchval("""
                    SELECT MAX(timestamp) FROM checkins WHERE user_id = $1 AND category = $2
                """, user_id, category)

                if last_checkin:
                    last_checkin_date = last_checkin.date()
                    current_date = datetime.utcnow().date()

                    if category in ["gym", "food"] and last_checkin_date == current_date:
                        return True  # Daily reset (not 24 hours)
                    if category == "weight" and last_checkin_date >= current_date - timedelta(days=7):
                        return True  # Weekly reset
                return False
            except Exception as e:
                print(f"❌ Error checking cooldown for user {user_id}: {e}")
                return False

    async def close(self):
        """Close the database connection."""
        if self.pool:
            await self.pool.close()
            print("🔴 Database connection closed.")

    async def add_user(self, user_id, username):
        """Add user to the database if they don’t exist."""
        async with self.pool.acquire() as conn:
            try:
                print(f"📝 Adding user {username} (ID: {user_id}) to database...")
                await conn.execute("""
                    INSERT INTO users (user_id, username, points)
                    VALUES ($1, $2, 0) ON CONFLICT (user_id) DO NOTHING
                """, user_id, username)
                print(f"✅ User {username} added successfully.")
            except Exception as e:
                print(f"❌ Error adding user {username}: {e}")

    async def log_checkin(self, user_id, category, image_hash=None):
        """Log a gym or food check-in and store image hash, while updating user points."""
        async with self.pool.acquire() as conn:
            try:
                if await self.check_cooldown(user_id, category):
                    print(f"⏳ User {user_id} is still on cooldown for {category}. Check-in denied.")
                    return "cooldown"

                print(f"📝 Logging check-in for user {user_id} in category {category} with image hash {image_hash}...")

                # Insert check-in record
                await conn.execute("""
                    INSERT INTO checkins (user_id, category, image_hash, timestamp)
                    VALUES ($1, $2, $3, NOW())
                """, user_id, category, image_hash)
                print("✅ Check-in recorded successfully!")

                # Ensure user exists in progress table (Fix ON CONFLICT issue)
                await conn.execute("""
                    INSERT INTO progress (user_id, total_gym_checkins, total_food_logs)
                    VALUES ($1, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                """, user_id)

                # Update progress tracking & points
                if category == "gym":
                    print("🔄 Updating progress & points for gym check-ins...")
                    await conn.execute("""
                        UPDATE progress SET total_gym_checkins = total_gym_checkins + 1 WHERE user_id = $1
                    """, user_id)
                    await conn.execute("""
                        UPDATE users SET points = points + 1 WHERE user_id = $1
                    """, user_id)
                    print("✅ Points updated for gym check-in!")

                elif category == "food":
                    print("🔄 Updating progress & points for food logs...")
                    await conn.execute("""
                        UPDATE progress SET total_food_logs = total_food_logs + 1 WHERE user_id = $1
                    """, user_id)
                    await conn.execute("""
                        UPDATE users SET points = points + 1 WHERE user_id = $1
                    """, user_id)
                    print("✅ Points updated for food check-in!")

                elif category == "weight":
                    print("🔄 Updating progress for weight logs...")
                    await conn.execute("""
                        UPDATE progress SET total_weight_change = total_weight_change + 1 WHERE user_id = $1
                    """, user_id)
                    await conn.execute("""
                        UPDATE users SET points = points + 1 WHERE user_id = $1
                    """, user_id)
                    print("✅ Points updated for weight check-in!")

            except Exception as e:
                print(f"❌ Error logging check-in for user {user_id}: {e}")

    async def get_progress(self, user_id):
        """Retrieve user progress (total check-ins, food logs, weight change)."""
        async with self.pool.acquire() as conn:
            try:
                print(f"📊 Fetching progress for user {user_id}...")
                result = await conn.fetchrow("""
                    SELECT total_gym_checkins, total_food_logs, total_weight_change
                    FROM progress WHERE user_id = $1
                """, user_id)
                print(f"✅ Progress retrieved: {result}")
                return result
            except Exception as e:
                print(f"❌ Error fetching progress: {e}")

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