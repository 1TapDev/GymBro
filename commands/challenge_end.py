# commands/challenge_end.py (Clean version with fixed function calls)
import discord
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from database import db
from discord import app_commands
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
        self.photo_reminders = {}
        self._task_started = False
        print("🔄 [ChallengeEnd] Initializing ChallengeEnd cog...")

    def cog_load(self):
        """Start tasks when cog is loaded"""
        if not self._task_started:
            self.check_challenge_end.start()
            self.check_photo_deadline.start()
            self._task_started = True
            print("✅ [ChallengeEnd] Tasks started successfully!")

    def cog_unload(self):
        """Stop tasks when cog is unloaded"""
        self.check_challenge_end.cancel()
        self.check_photo_deadline.cancel()
        self._task_started = False
        print("🛑 [ChallengeEnd] Tasks stopped")

    @tasks.loop(seconds=30)  # Check every 30 seconds for better debugging
    async def check_challenge_end(self):
        """Check if any challenges have ended and trigger photo collection"""
        current_time = datetime.now()
        print(f"🔍 [ChallengeEnd] Checking for ended challenges at {current_time}")

        try:
            async with db.pool.acquire() as conn:
                # Find challenges that just ended
                ended_challenges = await conn.fetch("""
                    SELECT id, name, end_date FROM challenges 
                    WHERE status = 'active' 
                    AND end_date <= NOW() 
                    AND COALESCE(photo_collection_started, FALSE) = FALSE
                """)

                if ended_challenges:
                    print(f"🏁 [ChallengeEnd] Found {len(ended_challenges)} challenges that need to end!")

                    for challenge in ended_challenges:
                        print(f"🎯 [ChallengeEnd] Processing challenge '{challenge['name']}' (ID: {challenge['id']})")
                        await self.start_photo_collection(challenge['id'], challenge['name'])

                        # Mark photo collection as started AND set status to avoid double processing
                        await conn.execute("""
                            UPDATE challenges 
                            SET photo_collection_started = TRUE,
                                photo_collection_deadline = NOW() + INTERVAL '%s hours'
                            WHERE id = $1 AND COALESCE(photo_collection_started, FALSE) = FALSE
                        """ % PHOTO_SUBMISSION_DEADLINE_HOURS, challenge['id'])

                        # Verify it was updated
                        updated = await conn.fetchval("""
                            SELECT photo_collection_started FROM challenges WHERE id = $1
                        """, challenge['id'])

                        if updated:
                            print(f"✅ [ChallengeEnd] Photo collection started for challenge {challenge['id']}")
                        else:
                            print(
                                f"⚠️ [ChallengeEnd] Challenge {challenge['id']} was already processed by another task")
                else:
                    print("ℹ️ [ChallengeEnd] No challenges need to end right now")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in check_challenge_end: {e}")
            import traceback
            traceback.print_exc()

    async def start_photo_collection(self, challenge_id, challenge_name):
        """DM all participants to submit final photos"""
        print(f"📸 [ChallengeEnd] Starting photo collection for challenge {challenge_id}")

        try:
            async with db.pool.acquire() as conn:
                # Double-check that this challenge hasn't already been processed
                already_started = await conn.fetchval("""
                    SELECT photo_collection_started FROM challenges 
                    WHERE id = $1
                """, challenge_id)

                if already_started:
                    print(f"⚠️ [ChallengeEnd] Challenge {challenge_id} photo collection already started, skipping...")
                    return

                # Get challenge info for notifications
                challenge_info = await conn.fetchrow("""
                    SELECT channel_id FROM challenges WHERE id = $1
                """, challenge_id)

                participants = await conn.fetch("""
                    SELECT user_id, username, submitted_final FROM challenge_participants 
                    WHERE challenge_id = $1 AND COALESCE(disqualified, FALSE) = FALSE
                """, challenge_id)

                print(f"👥 [ChallengeEnd] Found {len(participants)} participants for challenge {challenge_id}")

                # Send notification to the challenge channel
                if challenge_info and challenge_info['channel_id']:
                    channel = self.bot.get_channel(challenge_info['channel_id'])
                    if channel:
                        embed = discord.Embed(
                            title=f"🏁 Challenge '{challenge_name}' Has Ended!",
                            description=(
                                f"**📸 Final Photo Submission Phase**\n\n"
                                f"All participants have been DMed with instructions to submit their final photos.\n"
                                f"⏰ **Deadline:** 24 hours from now\n\n"
                                f"After everyone submits their photos, voting will begin!"
                            ),
                            color=discord.Color.orange()
                        )
                        await channel.send(embed=embed)
                        print(f"📢 [ChallengeEnd] Sent end notification to channel {challenge_info['channel_id']}")

                # DM all participants
                for participant in participants:
                    if participant["submitted_final"]:
                        print(f"📸 [ChallengeEnd] Skipping {participant['username']} — already submitted final photos.")
                        continue
                    user = await self.bot.get_user(participant['user_id'])
                    if user:
                        print(f"📩 [ChallengeEnd] Sending DM to {user.name} ({user.id})")
                        await self.send_final_photo_request(user, challenge_id, challenge_name)
                        # Start reminder task
                        task = asyncio.create_task(
                            self.photo_reminder_loop(user, challenge_id, challenge_name)
                        )
                        self.photo_reminders[f"{challenge_id}_{user.id}"] = task
                    else:
                        print(f"⚠️ [ChallengeEnd] Could not find user {participant['user_id']}")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in start_photo_collection: {e}")
            import traceback
            traceback.print_exc()

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
            print(f"✅ [ChallengeEnd] Sent final photo request to {user.name}")

            # Start collecting photos
            await self.collect_final_photos(user, challenge_id, dm)

        except discord.Forbidden:
            print(f"❌ [ChallengeEnd] Cannot DM user {user.name} - DMs disabled")
        except Exception as e:
            print(f"❌ [ChallengeEnd] Error sending final photo request to {user.name}: {e}")
            import traceback
            traceback.print_exc()

    async def collect_final_photos(self, user, challenge_id, dm_channel):
        """Collect final photos from user with sequential reference display"""
        photos = []
        target_photo_count = 4

        # Get user's initial photos for reference
        initial_photos = []
        pose_labels = [
            "📸 Upload your **Relaxed Front Pose** now:",
            "📸 Upload your **Front Double Biceps** now:",
            "📸 Upload your **Rear Double Biceps** now:",
            "📸 Upload your **Relaxed Back Pose** now:"
        ]

        try:
            async with db.pool.acquire() as conn:
                participant_data = await conn.fetchrow("""
                    SELECT initial_photos FROM challenge_participants 
                    WHERE challenge_id = $1 AND user_id = $2
                """, challenge_id, user.id)

                if participant_data and participant_data['initial_photos']:
                    initial_photos = participant_data['initial_photos'][:4]
                    print(f"📸 [ChallengeEnd] Found {len(initial_photos)} reference photos for {user.name}")
        except Exception as e:
            print(f"⚠️ [ChallengeEnd] Error getting initial photos: {e}")

        # Generate unique folder for final photos
        user_folder = os.path.join("challenge", str(challenge_id), "final", str(user.id))
        os.makedirs(user_folder, exist_ok=True)

        def check(m):
            return (m.author == user and m.channel == dm_channel and
                    (m.attachments or m.content.lower() in ['done', 'skip']))

        try:
            await dm_channel.send(f"📸 Please upload your {target_photo_count} final photos one by one:")

            while len(photos) < target_photo_count:
                photo_index = len(photos)

                # Show initial photo reference if available
                if photo_index < len(initial_photos) and os.path.exists(initial_photos[photo_index]):
                    try:
                        pose_name = pose_labels[photo_index].replace('📸 Upload your **', '').replace('** now:', '')
                        reference_label = f"📸 **Reference - {pose_name}:**"
                        await dm_channel.send(reference_label)
                        file = discord.File(initial_photos[photo_index], filename=f"reference_{photo_index + 1}.jpg")
                        await dm_channel.send(file=file)
                        print(f"📸 [ChallengeEnd] Sent reference photo {photo_index + 1} to {user.name}")
                    except Exception as e:
                        print(f"Error sending reference photo {photo_index + 1}: {e}")

                # Ask for user's photo
                if photo_index < len(pose_labels):
                    await dm_channel.send(pose_labels[photo_index])
                else:
                    await dm_channel.send(f"📸 Upload photo {photo_index + 1} of {target_photo_count}:")

                # Wait for photo submission
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=3600)  # 1 hour timeout per photo
                except asyncio.TimeoutError:
                    await dm_channel.send("⏰ Timeout waiting for photo. Continuing with next pose...")
                    continue

                if msg.content.lower() == 'skip':
                    await dm_channel.send(f"⏭️ Skipped photo {photo_index + 1}")
                    continue

                if msg.content.lower() == 'done' and len(photos) >= target_photo_count:
                    break

                if msg.attachments:
                    attachment = msg.attachments[0]  # Take first attachment
                    filename = f"final_{photo_index + 1}_{attachment.filename}"
                    photo_path = os.path.join(user_folder, filename)

                    try:
                        await attachment.save(photo_path)
                        photos.append(photo_path)
                        await dm_channel.send(f"✅ Photo {len(photos)}/{target_photo_count} received!")
                        print(f"✅ [ChallengeEnd] {user.name} submitted photo {len(photos)}/4")
                    except Exception as e:
                        print(f"❌ Error saving photo: {e}")
                        await dm_channel.send("❌ Error saving photo. Please try uploading again.")
                        continue
                else:
                    await dm_channel.send("❌ Please upload an image file.")

            if len(photos) == 0:
                await dm_channel.send("❌ No photos were submitted. You have been disqualified.")
                # Mark as disqualified
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE challenge_participants 
                        SET disqualified = TRUE, disqualification_reason = 'No final photos submitted'
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)
                return

            # Ask for final weight
            await dm_channel.send("⚖️ What is your final weight? (Enter a number like 175.5)")

            def weight_check(m):
                return m.author == user and m.channel == dm_channel and not m.attachments

            try:
                weight_msg = await self.bot.wait_for("message", check=weight_check, timeout=300)
                final_weight = float(weight_msg.content.strip())

                if final_weight <= 0 or final_weight > 1000:
                    raise ValueError("Weight out of reasonable range")

            except asyncio.TimeoutError:
                await dm_channel.send("⏰ Timeout waiting for weight. Using 0 as placeholder.")
                final_weight = 0.0
            except ValueError:
                await dm_channel.send("❌ Invalid weight format. Using 0 as placeholder.")
                final_weight = 0.0

            # Save to database
            try:
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE challenge_participants 
                        SET final_photos = $1, final_weight = $2, submitted_final = TRUE
                        WHERE challenge_id = $3 AND user_id = $4
                    """, photos, final_weight, challenge_id, user.id)

                await dm_channel.send("✅ Your final photos have been submitted! Good luck in the voting!")
                print(
                    f"✅ [ChallengeEnd] {user.name} completed final photo submission with {len(photos)} photos and weight {final_weight}")

                # Cancel reminder task
                task_key = f"{challenge_id}_{user.id}"
                if task_key in self.photo_reminders:
                    self.photo_reminders[task_key].cancel()
                    print(f"🛑 [ChallengeEnd] Cancelled reminder task for {user.name}")

            except Exception as e:
                print(f"❌ [ChallengeEnd] Database error saving final photos for {user.name}: {e}")
                await dm_channel.send("❌ Error saving your submission to database. Please contact an administrator.")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in collect_final_photos for {user.name}: {e}")
            await dm_channel.send("❌ An unexpected error occurred. Please contact an administrator.")
            import traceback
            traceback.print_exc()

    async def photo_reminder_loop(self, user, challenge_id, challenge_name):
        """Send hourly reminders in the last 6 hours"""
        await asyncio.sleep(PHOTO_REMINDER_START_HOURS * 3600)

        for hours_left in range(REMINDER_HOURS_THRESHOLD, 0, -PHOTO_REMINDER_INTERVAL_HOURS):
            try:
                async with db.pool.acquire() as conn:
                    submitted = await conn.fetchval("""
                        SELECT COALESCE(submitted_final, FALSE) FROM challenge_participants
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)

                if submitted:
                    return

                dm = await user.create_dm()
                embed = discord.Embed(
                    title=f"⏰ {hours_left} Hours Left!",
                    description=f"Don't forget to submit your final photos for **{challenge_name}**!",
                    color=discord.Color.orange() if hours_left > 3 else discord.Color.red()
                )
                await dm.send(embed=embed)

                await asyncio.sleep(PHOTO_REMINDER_INTERVAL_HOURS * 3600)

            except Exception as e:
                print(f"❌ [ChallengeEnd] Error sending reminder: {e}")

    @app_commands.command(name="resend_final_dm", description="Resend DMs to users who haven’t submitted final photos.")
    @app_commands.checks.has_permissions(administrator=True)
    async def resend_final_dm(self, interaction: discord.Interaction, challenge_id: int):
        await interaction.response.send_message("🔄 Resending DMs...", ephemeral=True)

        async with db.pool.acquire() as conn:
            challenge = await conn.fetchrow("SELECT name FROM challenges WHERE id = $1", challenge_id)
            if not challenge:
                await interaction.followup.send("❌ Challenge not found.")
                return

            participants = await conn.fetch("""
                SELECT user_id, username, submitted_final FROM challenge_participants 
                WHERE challenge_id = $1 AND COALESCE(disqualified, FALSE) = FALSE
            """, challenge_id)

        count = 0
        for p in participants:
            if p["submitted_final"]:
                continue

            try:
                user = await self.bot.fetch_user(p["user_id"])
                await self.send_final_photo_request(user, challenge_id, challenge["name"])
                count += 1
            except Exception as e:
                print(f"❌ Failed to resend final DM to {p['username']}: {e}")

        await interaction.followup.send(f"📩 DMs resent to {count} users.")

    @tasks.loop(minutes=5)  # Check every 5 minutes
    async def check_photo_deadline(self):
        """Check if photo collection deadline has passed and start voting"""
        print("🗳️ [ChallengeEnd] Checking photo deadlines...")

        try:
            async with db.pool.acquire() as conn:
                ready_challenges = await conn.fetch("""
                    SELECT id, name, channel_id FROM challenges 
                    WHERE status = 'active' 
                    AND COALESCE(photo_collection_started, FALSE) = TRUE 
                    AND COALESCE(voting_started, FALSE) = FALSE
                    AND photo_collection_deadline <= NOW()
                """)

                if ready_challenges:
                    print(f"🎯 [ChallengeEnd] Found {len(ready_challenges)} challenges ready for voting")

                    for challenge in ready_challenges:
                        print(f"🗳️ [ChallengeEnd] Starting voting for challenge: {challenge['name']}")
                        # Import here to avoid circular imports
                        from .challenge_voting import ChallengeVoting
                        voting_cog = ChallengeVoting(self.bot)
                        await voting_cog.start_voting(challenge['id'], challenge['name'], challenge['channel_id'])
                        await conn.execute("""
                            UPDATE challenges SET voting_started = TRUE WHERE id = $1
                        """, challenge['id'])
                else:
                    print("ℹ️ [ChallengeEnd] No challenges ready for voting")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in check_photo_deadline: {e}")

    # Add a manual command to force check challenges (for debugging)
    @commands.command(name="debug_challenges")
    @commands.has_permissions(administrator=True)
    async def debug_challenges(self, ctx):
        """Debug command to manually check challenge status"""
        await ctx.send("🔍 Manually checking challenge status...")
        await self.check_challenge_end()
        await ctx.send("✅ Challenge check completed! Check console for details.")


async def setup(bot):
    await bot.add_cog(ChallengeEnd(bot))