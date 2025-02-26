import discord
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from database import db  # Import your database methods

# Define the scheduler
scheduler = AsyncIOScheduler()

# Set Timezone (Eastern Standard Time)
EST = pytz.timezone("America/New_York")


async def fetch_top_weight_changes():
    """ Fetch the top 3 users with the most weight change this week. """
    async with db.pool.acquire() as conn:
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

        return rows  # Returns top 3 users with the biggest weight change (gain or loss)


async def send_weigh_in_reminder(bot):
    """ Sends a weigh-in reminder every Saturday at 12 PM EST. """
    guild_id = 1343077263704592436  # Replace with your Discord server ID
    channel_id = 1343077263704592439  # Replace with the channel where you want to send the message

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # Fetch top 3 weight changes
    top_weight_changes = await fetch_top_weight_changes()

    if top_weight_changes:
        leaderboard_entries = []
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(top_weight_changes):
            user = await bot.fetch_user(row["user_id"])
            username = user.display_name if user else "Unknown"
            first_weight = row["first_weight"]
            recent_weight = row["recent_weight"]
            weight_change = row["weight_change"]

            # Adjust emoji based on weight change
            trend_emoji = "🔼" if weight_change > 0 else "🔽"

            leaderboard_entries.append(
                f"{medals[idx]} **{username}** [{first_weight} → {recent_weight}] **{weight_change}** lbs {trend_emoji}"
            )

        leaderboard_text = "\n".join(leaderboard_entries)
    else:
        leaderboard_text = "No weigh-in data available for this week."

    # Weigh-In Reminder Message
    reminder_message = f"""
📢 @everyone It's **Weigh-In Saturday**! ⚖️  
Don't forget to log your weight check-in today!  

📝 **Use `/checkin weight` to log your weight now!**  

#️⃣ **Top 3 Weight Changes This Week:**  
{leaderboard_text}

✅ **Stay accountable! See you next week!**
"""

    await channel.send(reminder_message)


def start_scheduler(bot):
    """ Starts the APScheduler to send reminders every Saturday at 12 PM EST. """
    est = pytz.timezone("America/New_York")

    # Schedule the weigh-in reminder for every Saturday at 12 PM EST
    scheduler.add_job(send_weigh_in_reminder, "cron", day_of_week="wed", hour=1, minute=41, timezone=est, args=[bot])

    scheduler.start()