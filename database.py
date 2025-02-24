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

                if last_checkin:
                    # Convert last check-in timestamp to EST
                    last_checkin_time_utc = last_checkin["timestamp"].replace(tzinfo=pytz.utc)
                    last_checkin_time_est = last_checkin_time_utc.astimezone(EST)

                    if category in ["gym", "food"]:
                        # Get midnight EST for the next day
                        next_available_time = datetime.combine(last_checkin_time_est.date() + timedelta(days=1),
                                                               datetime.min.time(), EST)

                        if current_time_est < next_available_time:
                            remaining_time = next_available_time - current_time_est
                            hours, minutes = divmod(int(remaining_time.total_seconds()) // 60, 60)

                    elif category == "weight":
                        # Get the next available weight check-in time (7 days later)
                        next_available_time = last_checkin_time_est + timedelta(days=7)

                        if current_time_est < next_available_time:
                            remaining_time = next_available_time - current_time_est
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

    async def log_checkin(self, user_id, category, image_hash):
        """Log a check-in only after the image is confirmed, and update points dynamically."""
        async with self.pool.acquire() as conn:
            try:
                if await self.check_cooldown(user_id, category):
                    print(f"⏳ User {user_id} is still on cooldown for {category}. Check-in denied.")
                    return "cooldown"

                print(f"📝 Logging check-in for user {user_id} in category {category} with image hash {image_hash}...")

                # Ensure an image is provided
                if not image_hash:
                    print("❌ No valid image uploaded. Check-in will NOT be recorded.")
                    return "no_image"

                # Insert check-in record **only after image is provided**
                await conn.execute("""
                    INSERT INTO checkins (user_id, category, image_hash, timestamp)
                    VALUES ($1, $2, $3, NOW())
                """, user_id, category, image_hash)
                print("✅ Check-in recorded successfully!")

                # Update progress tracking
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
                        UPDATE progress SET total_weight_change = total_weight_change + 1 WHERE user_id = $1
                    """, user_id)

                # Fetch updated points dynamically
                updated_points = await self.get_user_points(user_id)

                # Ensure points are updated in `users` table
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
        """Retrieve user progress (total check-ins, food logs, weight change)."""
        async with self.pool.acquire() as conn:
            try:
                return await conn.fetchrow("""
                    SELECT total_gym_checkins, total_food_logs, total_weight_change
                    FROM progress WHERE user_id = $1
                """, user_id)
            except Exception as e:
                return None  # Return None if there's an error instead of printing

    async def update_pr(self, user_id, lift, value):
        """Update the user's personal record (PR) for deadlift, bench, or squat, ensuring they have an entry."""
        async with self.pool.acquire() as conn:
            try:
                print(f"📝 Checking if user {user_id} has a personal record entry...")

                # Ensure user exists in `personal_records` before updating
                await conn.execute("""
                    INSERT INTO personal_records (user_id, deadlift, bench, squat)
                    VALUES ($1, 0, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING;
                """, user_id)
                print(f"✅ Ensured PR row exists for user {user_id}.")

                # Now update the PR value for the specific lift
                update_query = f"""
                    UPDATE personal_records 
                    SET {lift} = $1 
                    WHERE user_id = $2;
                """
                await conn.execute(update_query, value, user_id)

                print(f"✅ PR successfully updated for {user_id}: {lift.capitalize()} set to {value} lbs.")

                # Fetch updated PR record to verify the change
                pr_after_update = await self.get_personal_records(user_id)
                print(f"✅ PR after update for {user_id}: {pr_after_update}")

            except Exception as e:
                print(f"❌ Error updating PR for {user_id}: {e}")

    async def get_personal_records(self, user_id):
        """Retrieve a user's personal records (PRs), ensuring defaults if not found."""
        async with self.pool.acquire() as conn:
            try:
                print(f"🔍 Retrieving PR records from database for user {user_id}...")
                record = await conn.fetchrow("""
                    SELECT deadlift, bench, squat FROM personal_records WHERE user_id = $1
                """, user_id)

                if not record:
                    print(f"⚠️ No personal records found for {user_id}. Returning defaults (0s).")
                    return {"deadlift": 0, "bench": 0, "squat": 0}  # Default PRs

                print(f"✅ PR records retrieved for user {user_id}: {record}")
                return dict(record)  # Convert asyncpg Record to dictionary
            except Exception as e:
                print(f"❌ Error retrieving PR records for {user_id}: {e}")
                return {"deadlift": 0, "bench": 0, "squat": 0}  # Return defaults on error

    async def get_leaderboard(self):
        """Retrieve the top 10 users by points."""
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT username, points FROM users ORDER BY points DESC LIMIT 10
            """)

db = Database()