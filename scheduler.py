import discord
import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import db

scheduler = AsyncIOScheduler()
EST = pytz.timezone("America/New_York")


async def check_users_in_challenge(bot):
    """Checks if users are in the active challenge and notifies those who haven't joined yet."""
    print("🔍 [Scheduler] Checking challenge participation...")

    guild_id = 1343077263704592436  # Discord server ID
    channel_id = 1343077263704592439  # Channel for challenge notifications

    guild = bot.get_guild(guild_id)
    if not guild:
        print("❌ [Scheduler] Guild not found!")
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        print("❌ [Scheduler] Channel not found!")
        return

    async with db.pool.acquire() as conn:
        print("📡 [Scheduler] Fetching active challenge...")

        try:
            active_challenge = await conn.fetchrow("SELECT id FROM challenges WHERE status = 'active'")
            if not active_challenge:
                print("⚠️ [Scheduler] No active challenge found. Skipping check.")
                return

            challenge_id = active_challenge["id"]
            print(f"✅ [Scheduler] Active challenge ID: {challenge_id}")

            print("📡 [Scheduler] Fetching registered users...")
            registered_users = await conn.fetch("SELECT user_id, username FROM users")
            print(f"✅ [Scheduler] Retrieved {len(registered_users)} registered users.")

            print("📡 [Scheduler] Fetching challenge participants...")
            challenge_users = await conn.fetch("SELECT user_id FROM challenge_participants WHERE challenge_id = $1", challenge_id)
            print(f"✅ [Scheduler] Retrieved {len(challenge_users)} users in the challenge.")

            challenge_user_ids = {row["user_id"] for row in challenge_users}
            missing_users = [
                f"<@{user['user_id']}>" for user in registered_users if user["user_id"] not in challenge_user_ids
            ]

            if missing_users:
                missing_users_list = ", ".join(missing_users)
                message = (
                    f"⚠️ **The following users haven't joined the challenge yet!**\n"
                    f"{missing_users_list}\n\n"
                    f"📌 Use **`/join_challenge`** to participate and track your progress!"
                )
                print(f"📢 [Scheduler] Sending challenge reminder: {missing_users_list}")
                await channel.send(message)
            else:
                print("✅ [Scheduler] All users are in the challenge. No reminder needed.")

        except Exception as e:
            print(f"❌ [Scheduler] Error during challenge check: {e}")

    print("✅ [Scheduler] Challenge participation check completed.")


async def send_weigh_in_reminder(bot):
    """ Sends a weigh-in reminder every Saturday at 12 PM EST as an embed. """
    print("🔍 [Scheduler] Sending weigh-in reminder...")
    guild_id = 1119801250230321273  # Discord server ID
    channel_id = 1235378047390187601  # Channel for weigh-in notifications

    guild = bot.get_guild(guild_id)
    if not guild:
        print("❌ [Scheduler] Guild not found!")
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        print("❌ [Scheduler] Channel not found!")
        return

    async with db.pool.acquire() as conn:
        try:
            rows = await conn.fetch("""
                WITH weight_data AS (
                    SELECT user_id, 
                        MIN(weight) AS first_weight,
                        MAX(weight) AS recent_weight
                    FROM checkins
                    WHERE category = 'weight' 
                    AND timestamp >= NOW() - INTERVAL '7 days'
                    GROUP BY user_id
                )
                SELECT user_id, first_weight, recent_weight, (recent_weight - first_weight) AS weight_change
                FROM weight_data
                ORDER BY ABS(recent_weight - first_weight) DESC
                LIMIT 3;
            """)

            leaderboard_text = ""
            medals = ["🥇", "🥈", "🥉"]
            for idx, row in enumerate(rows):
                user = await bot.fetch_user(row["user_id"])
                username = user.display_name if user else "Unknown"
                first_weight = row["first_weight"]
                recent_weight = row["recent_weight"]
                weight_change = row["weight_change"]
                trend_emoji = "🔼" if weight_change > 0 else "🔽"

                leaderboard_text += f"{medals[idx]} **{username}** [{first_weight} → {recent_weight}] **{weight_change} lbs** {trend_emoji}\n"

            if not leaderboard_text:
                leaderboard_text = "No weigh-in data available for this week."

            embed = discord.Embed(
                title="📢 It's Weigh-In Saturday! ⚖️",
                description="Don't forget to log your weight check-in today!",
                color=discord.Color.blue()
            )
            embed.add_field(name="📝 Log Your Weight", value="Use **`/checkin weight`** to log your weight now!", inline=False)
            embed.add_field(name="🏆 Top 3 Weight Changes This Week", value=leaderboard_text, inline=False)
            embed.set_footer(text="✅ Stay accountable! See you next week!")

            await channel.send(content="@everyone", embed=embed)
            print("✅ [Scheduler] Sent weigh-in reminder.")

        except Exception as e:
            print(f"❌ [Scheduler] Error sending weigh-in reminder: {e}")


def start_scheduler(bot):
    """ Starts the APScheduler to send reminders and check challenge participation. """
    print("⏳ [Scheduler] Initializing APScheduler...")
    est = pytz.timezone("America/New_York")

    # ✅ Check every 12 hours if users are in the challenge
    scheduler.add_job(check_users_in_challenge, "interval", hours=12, timezone=est, args=[bot])

    # ✅ Weigh-in reminder every Saturday at 12 PM EST
    scheduler.add_job(send_weigh_in_reminder, "cron", day_of_week="sat", hour=9, minute=30, timezone=est, args=[bot])

    scheduler.start()
    print("✅ [Scheduler] APScheduler Started: Checking challenge participation every 12 hours + Weigh-In reminder on Saturdays.")

    async def run_initial_check():
        await asyncio.sleep(5)  # Give the bot time to fully initialize
        print("🚀 [Scheduler] Running initial challenge participation check...")
        await check_users_in_challenge(bot)

    bot.loop.create_task(run_initial_check())
