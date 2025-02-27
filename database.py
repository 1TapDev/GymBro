import asyncpg
import os
import pytz  # Library for timezone conversion
from datetime import datetime, timedelta

EST = pytz.timezone("America/New_York")  # Define Eastern Standard Time

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
        """Check if a user is on cooldown by reading the timestamp from the checkins table (in EST)."""
        async with self.pool.acquire() as conn:
            try:
                last_checkin = await conn.fetchrow("""
                    SELECT timestamp FROM checkins 
                    WHERE user_id = $1 AND category = $2 
                    ORDER BY timestamp DESC LIMIT 1
                """, user_id, category)

                # Get current time in UTC and convert to EST
                current_time_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
                current_time_est = current_time_utc.astimezone(EST)
                today_est = current_time_est.date()  # Get today's date in EST

                if last_checkin:
                    # Convert last check-in timestamp to EST
                    last_checkin_time_utc = last_checkin["timestamp"].replace(tzinfo=pytz.utc)
                    last_checkin_time_est = last_checkin_time_utc.astimezone(EST)
                    last_checkin_date = last_checkin_time_est.date()  # Get last check-in date

                    if category in ["gym", "food"]:
                        # User must wait until midnight EST
                        next_reset = datetime.combine(today_est + timedelta(days=1), datetime.min.time(), EST)
                        if last_checkin_date == today_est:
                            remaining_time = next_reset - current_time_est
                            hours, minutes = divmod(int(remaining_time.total_seconds()) // 60, 60)
                            return f"⏳ You have already checked in for **{category}** today. Try again in **{hours}h {minutes}m** (after midnight EST)!"

                    elif category == "weight":
                        # User must wait until next **Sunday**
                        last_sunday = last_checkin_date - timedelta(days=last_checkin_date.weekday() + 1)  # Find last Sunday
                        next_sunday = last_sunday + timedelta(days=7)  # Find next Sunday

                        if current_time_est < datetime.combine(next_sunday, datetime.min.time(), EST):
                            remaining_time = datetime.combine(next_sunday, datetime.min.time(), EST) - current_time_est
                            days, remainder = divmod(int(remaining_time.total_seconds()), 86400)
                            hours, minutes = divmod(remainder // 60, 60)
                            return f"⏳ You have already checked in for **{category}** this week. Try again in **{days}d {hours}h {minutes}m**."

                return None  # No cooldown, user can check in

            except Exception as e:
                print(f"❌ Error checking cooldown for user {user_id}: {e}")
                return None

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

    async def log_checkin(self, user_id, category, image_hash, image_path, workout=None, weight=None, meal=None):
        """Log a check-in only after the image is confirmed, store image path, and update points dynamically."""
        async with self.pool.acquire() as conn:
            try:
                if await self.check_cooldown(user_id, category):
                    print(f"⏳ User {user_id} is still on cooldown for {category}. Check-in denied.")
                    return "cooldown"

                print(f"📝 Logging check-in for user {user_id} in category {category} with image path {image_path}...")

                if not image_hash:
                    print("❌ No valid image uploaded. Check-in will NOT be recorded.")
                    return "no_image"

                # ✅ Ensure user exists in `users` table before inserting check-ins
                await conn.execute("""
                    INSERT INTO users (user_id, username, points)
                    VALUES ($1, 'Unknown', 0) 
                    ON CONFLICT (user_id) DO NOTHING
                """, user_id)

                # ✅ Ensure user exists in `progress` table before inserting check-in
                await conn.execute("""
                    INSERT INTO progress (user_id, total_gym_checkins, total_food_logs, total_weight_change)
                    VALUES ($1, 0, 0, 0) 
                    ON CONFLICT (user_id) DO NOTHING
                """, user_id)

                # ✅ Insert check-in record
                await conn.execute("""
                    INSERT INTO checkins (user_id, category, image_hash, image_path, workout, weight, meal, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                """, user_id, category, image_hash, image_path, workout, weight, meal)

                print("✅ Check-in recorded successfully!")

                # ✅ Update progress tracking
                if category == "gym":
                    await conn.execute("""
                        UPDATE progress SET total_gym_checkins = total_gym_checkins + 1 WHERE user_id = $1
                    """, user_id)
                elif category == "food":
                    await conn.execute("""
                        UPDATE progress SET total_food_logs = total_food_logs + 1 WHERE user_id = $1
                    """, user_id)
                elif category == "weight":
                    await conn.execute("""
                        UPDATE progress SET total_weight_change = $1 WHERE user_id = $2
                    """, weight, user_id)

                # ✅ Fetch updated points dynamically
                updated_points = await self.get_user_points(user_id)

                # ✅ Ensure points are updated in `users` table
                await conn.execute("""
                    UPDATE users SET points = $1 WHERE user_id = $2
                """, updated_points, user_id)

                print(f"🏆 Updated points for user {user_id}: {updated_points}")

                return "success"

            except Exception as e:
                print(f"❌ Error logging check-in for user {user_id}: {e}")
                return "error"

    async def get_user_points(self, user_id):
        """Calculate total points based on check-ins (excluding duplicates)."""
        async with self.pool.acquire() as conn:
            try:
                total_points = await conn.fetchval("""
                    SELECT COUNT(*) FROM checkins 
                    WHERE user_id = $1
                """, user_id)

                return total_points if total_points else 0
            except Exception as e:
                print(f"❌ Error fetching points for user {user_id}: {e}")
                return 0

    async def get_progress(self, user_id):
        """Retrieve user progress directly from checkins table instead of relying on progress table."""
        async with self.pool.acquire() as conn:
            try:
                # Count total gym check-ins from checkins table
                total_gym_checkins = await conn.fetchval("""
                    SELECT COUNT(*) FROM checkins WHERE user_id = $1 AND category = 'gym'
                """, user_id) or 0

                # Count total food logs from checkins table
                total_food_logs = await conn.fetchval("""
                    SELECT COUNT(*) FROM checkins WHERE user_id = $1 AND category = 'food'
                """, user_id) or 0

                return {
                    "total_gym_checkins": total_gym_checkins,
                    "total_food_logs": total_food_logs
                }
            except Exception as e:
                print(f"❌ Error fetching progress for user {user_id}: {e}")
                return None

    async def get_user_checkins(self, user_id, category):
        """Retrieve check-in history for a user based on category, including image paths."""
        async with self.pool.acquire() as conn:
            try:
                checkins = await conn.fetch("""
                    SELECT timestamp, workout, weight, meal, image_path FROM checkins 
                    WHERE user_id = $1 AND category = $2 
                    ORDER BY timestamp DESC
                """, user_id, category)

                return checkins
            except Exception as e:
                print(f"❌ Error fetching check-ins for user {user_id}: {e}")
                return []

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

    async def get_weight_change(self, user_id):
        """Fetch first & most recent weight entries for progress tracking."""
        async with self.pool.acquire() as conn:
            try:
                print(f"🔍 Fetching weight change for user {user_id}...")

                result = await conn.fetch("""
                    (SELECT weight, timestamp FROM checkins WHERE user_id = $1 AND category = 'weight' ORDER BY timestamp ASC LIMIT 1)
                    UNION ALL
                    (SELECT weight, timestamp FROM checkins WHERE user_id = $1 AND category = 'weight' ORDER BY timestamp DESC LIMIT 1);
                """, user_id)

                print(f"📊 Database returned {len(result)} weight entries for user {user_id}")

                if result:
                    for i, row in enumerate(result):
                        print(f"🔹 Entry {i + 1}: Weight = {row['weight']}, Timestamp = {row['timestamp']}")

                if len(result) == 2:
                    first_weight = float(result[0]["weight"])
                    recent_weight = float(result[1]["weight"])
                    weight_change = round(recent_weight - first_weight, 2)

                    print(
                        f"⚖️ Weight Change Calculated: First Weight = {first_weight}, Recent Weight = {recent_weight}, Change = {weight_change}")
                    return first_weight, recent_weight, weight_change

                print(f"❌ Insufficient weight entries for user {user_id} (Needs at least 2)")
                return None, None, None

            except Exception as e:
                print(f"❌ Error fetching weight change for user {user_id}: {e}")
                return None, None, None

    async def get_pr_rankings(self):
        """Retrieve the top 8 users for each PR category."""
        async with self.pool.acquire() as conn:
            rankings = {}

            for lift in ["deadlift", "bench", "squat"]:
                rows = await conn.fetch(f"""
                    SELECT user_id, {lift} FROM personal_records
                    WHERE {lift} IS NOT NULL
                    ORDER BY {lift} DESC
                    LIMIT 8
                """)

                rankings[lift] = [(row["user_id"], row[lift]) for row in rows]

            return rankings

    async def get_leaderboard(self):
        """Retrieve the top 10 users by points."""
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT username, points FROM users ORDER BY points DESC LIMIT 10
            """)

async def get_weekly_weight_changes(self):
    """ Fetch top 3 users with the highest weight change in the last 7 days """
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH recent_weights AS (
                SELECT 
                    user_id, weight, timestamp,
                    FIRST_VALUE(weight) OVER (PARTITION BY user_id ORDER BY timestamp ASC) AS first_weight,
                    LAST_VALUE(weight) OVER (PARTITION BY user_id ORDER BY timestamp DESC) AS last_weight
                FROM checkins
                WHERE category = 'weight' 
                AND timestamp >= NOW() - INTERVAL '7 days'
            )
            SELECT 
                users.username, 
                (MAX(last_weight) - MIN(first_weight)) AS weight_change
            FROM recent_weights
            JOIN users ON users.user_id = recent_weights.user_id
            GROUP BY users.username
            ORDER BY weight_change ASC  -- Sort by most weight lost
            LIMIT 3;
        """)

        return [(row["username"], row["weight_change"]) for row in rows]

db = Database()