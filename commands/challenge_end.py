# commands/challenge_end.py
import discord
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from database import db
import pytz

NYC_TZ = pytz.timezone("America/New_York")

# Configurable settings
PHOTO_SUBMISSION_DEADLINE_HOURS = 24
PHOTO_REMINDER_START_HOURS = 18
PHOTO_REMINDER_INTERVAL_HOURS = 1
REMINDER_HOURS_THRESHOLD = 6

class ChallengeEnd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_challenge_end.start()
        self.photo_reminders = {}  # Track reminder tasks

    @tasks.loop(minutes=30)  # Check every 30 minutes
    async def check_challenge_end(self):
        """Check if any challenges have ended and trigger photo collection"""
        async with db.pool.acquire() as conn:
            # Find challenges that just ended
            ended_challenges = await conn.fetch("""
                SELECT id, name FROM challenges 
                WHERE status = 'active' 
                AND end_date <= NOW() 
                AND photo_collection_started = FALSE
            """)

            for challenge in ended_challenges:
                await self.start_photo_collection(challenge['id'], challenge['name'])

                # Mark photo collection as started
                await conn.execute(f"""
                    UPDATE challenges 
                    SET photo_collection_started = TRUE,
                        photo_collection_deadline = NOW() + INTERVAL '{PHOTO_SUBMISSION_DEADLINE_HOURS} hours'
                    WHERE id = $1
                """, challenge['id'])

    async def start_photo_collection(self, challenge_id, challenge_name):
        """DM all participants to submit final photos"""
        async with db.pool.acquire() as conn:
            participants = await conn.fetch("""
                SELECT user_id, username FROM challenge_participants 
                WHERE challenge_id = $1 AND disqualified = FALSE
            """, challenge_id)

            for participant in participants:
                user = self.bot.get_user(participant['user_id'])
                if user:
                    await self.send_final_photo_request(user, challenge_id, challenge_name)
                    # Start reminder task
                    task = asyncio.create_task(
                        self.photo_reminder_loop(user, challenge_id, challenge_name)
                    )
                    self.photo_reminders[f"{challenge_id}_{user.id}"] = task

    async def send_final_photo_request(self, user, challenge_id, challenge_name):
        """Send DM requesting final photos"""
        try:
            embed = discord.Embed(
                title=f"🏁 Challenge '{challenge_name}' Has Ended!",
                description=(
                    "**Congratulations on completing the challenge!**\n\n"
                    "📸 Please submit your **4 final photos** following the same poses:\n"
                    "1. Relaxed Front Pose\n"
                    "2. Front Double Biceps\n"
                    "3. Rear Double Biceps\n"
                    "4. Relaxed Back Pose\n\n"
                    "⏰ **You have 24 hours to submit your photos!**"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="Reply with your photos below ⬇️")

            dm = await user.create_dm()
            await dm.send(embed=embed)

            # Show example photos again
            example_photos = ["assets/example.png", "assets/example1.png",
                              "assets/example2.png", "assets/example3.png"]
            await dm.send(files=[discord.File(photo) for photo in example_photos])

            # Wait for photos
            await self.collect_final_photos(user, challenge_id, dm)

        except discord.Forbidden:
            print(f"Cannot DM user {user.name}")

    async def collect_final_photos(self, user, challenge_id, dm_channel):
        """Collect final photos from user"""
        photos = []

        # Generate unique folder for final photos
        user_folder = os.path.join("challenge", str(challenge_id), "final", str(user.id))
        os.makedirs(user_folder, exist_ok=True)

        def check(m):
            return (m.author == user and m.channel == dm_channel and
                    (m.attachments or m.content.lower() in ['done', 'skip']))

        try:
            await dm_channel.send("📸 Please upload your 4 final photos:")

            while len(photos) < 4:
                msg = await self.bot.wait_for("message", check=check, timeout=3600)

                if msg.content.lower() == 'skip':
                    break

                for attachment in msg.attachments:
                    if len(photos) < 4:
                        filename = f"final_{len(photos) + 1}_{attachment.filename}"
                        photo_path = os.path.join(user_folder, filename)
                        await attachment.save(photo_path)
                        photos.append(photo_path)

                if len(photos) < 4:
                    await dm_channel.send(f"✅ Received {len(photos)}/4 photos. Please upload {4 - len(photos)} more.")

            # Optional additional photos
            await dm_channel.send("Would you like to upload additional poses? Send them now or type 'done'.")

            while True:
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=300)
                    if msg.content.lower() == 'done':
                        break
                    for attachment in msg.attachments:
                        filename = f"final_extra_{len(photos) + 1}_{attachment.filename}"
                        photo_path = os.path.join(user_folder, filename)
                        await attachment.save(photo_path)
                        photos.append(photo_path)
                except asyncio.TimeoutError:
                    break

            # Ask for final weight
            await dm_channel.send("⚖️ What is your final weight?")
            weight_msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == user and m.channel == dm_channel,
                timeout=300
            )
            final_weight = float(weight_msg.content)

            # Save to database
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE challenge_participants 
                    SET final_photos = $1, final_weight = $2, submitted_final = TRUE
                    WHERE challenge_id = $3 AND user_id = $4
                """, photos, final_weight, challenge_id, user.id)

            await dm_channel.send("✅ Your final photos have been submitted! Good luck in the voting!")

            # Cancel reminder task
            task_key = f"{challenge_id}_{user.id}"
            if task_key in self.photo_reminders:
                self.photo_reminders[task_key].cancel()

        except asyncio.TimeoutError:
            await dm_channel.send("⏰ Time's up! You can still submit photos within the 24-hour deadline.")
        except ValueError:
            await dm_channel.send("❌ Invalid weight format. Please try again.")

    async def photo_reminder_loop(self, user, challenge_id, challenge_name):
        """Send hourly reminders in the last 6 hours"""
        await asyncio.sleep(PHOTO_REMINDER_START_HOURS * 3600)

        for hours_left in range(REMINDER_HOURS_THRESHOLD, 0, -PHOTO_REMINDER_INTERVAL_HOURS):
            try:
                # Check if already submitted
                async with db.pool.acquire() as conn:
                    submitted = await conn.fetchval("""
                        SELECT submitted_final FROM challenge_participants
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)

                if submitted:
                    return

                # Send reminder
                dm = await user.create_dm()
                embed = discord.Embed(
                    title=f"⏰ {hours_left} Hours Left!",
                    description=f"Don't forget to submit your final photos for **{challenge_name}**!",
                    color=discord.Color.orange() if hours_left > 3 else discord.Color.red()
                )
                await dm.send(embed=embed)

                await asyncio.sleep(PHOTO_REMINDER_INTERVAL_HOURS * 3600)

            except Exception as e:
                print(f"Error sending reminder: {e}")

        # Final check - disqualify if not submitted
        async with db.pool.acquire() as conn:
            submitted = await conn.fetchval("""
                SELECT submitted_final FROM challenge_participants
                WHERE challenge_id = $1 AND user_id = $2
            """, challenge_id, user.id)

            if not submitted:
                await conn.execute("""
                    UPDATE challenge_participants 
                    SET disqualified = TRUE, disqualification_reason = 'No final photos submitted'
                    WHERE challenge_id = $1 AND user_id = $2
                """, challenge_id, user.id)

    @tasks.loop(hours=1)
    async def check_photo_deadline(self):
        """Check if photo collection deadline has passed and start voting"""
        async with db.pool.acquire() as conn:
            ready_challenges = await conn.fetch("""
                SELECT id, name, channel_id FROM challenges 
                WHERE status = 'active' 
                AND photo_collection_started = TRUE 
                AND voting_started = FALSE
                AND photo_collection_deadline <= NOW()
            """)

            for challenge in ready_challenges:
                await self.start_voting(challenge['id'], challenge['name'], challenge['channel_id'])
                await conn.execute("""
                    UPDATE challenges SET voting_started = TRUE WHERE id = $1
                """, challenge['id'])


async def setup(bot):
    await bot.add_cog(ChallengeEnd(bot))