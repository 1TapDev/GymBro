# commands/challenge_end.py (Fixed version with proper imports and function calls)
import discord
import asyncio
import os
import uuid
import traceback
import pytz
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from database import db
from discord import app_commands
from utils.shared import send_final_photo_request

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
                # Find challenges that just ended OR challenges that ended but still have participants needing DMs
                ended_challenges = await conn.fetch("""
                    SELECT DISTINCT c.id, c.name, c.end_date 
                    FROM challenges c
                    WHERE c.status = 'active' 
                    AND c.end_date <= NOW() 
                    AND (
                        -- Either photo collection hasn't started yet
                        COALESCE(c.photo_collection_started, FALSE) = FALSE
                        OR
                        -- Or there are still participants who need final DMs
                        EXISTS (
                            SELECT 1 FROM challenge_participants cp 
                            WHERE cp.challenge_id = c.id 
                            AND COALESCE(cp.disqualified, FALSE) = FALSE
                            AND COALESCE(cp.submitted_final, FALSE) = FALSE
                            AND COALESCE(cp.final_dm_sent, FALSE) = FALSE
                        )
                    )
                """)

                if ended_challenges:
                    print(f"🏁 [ChallengeEnd] Found {len(ended_challenges)} challenges that need processing!")

                    for challenge in ended_challenges:
                        print(f"🎯 [ChallengeEnd] Processing challenge '{challenge['name']}' (ID: {challenge['id']})")
                        await self.start_photo_collection(challenge['id'], challenge['name'])
                else:
                    print("ℹ️ [ChallengeEnd] No challenges need processing right now")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in check_challenge_end: {e}")
            traceback.print_exc()

    @check_challenge_end.before_loop
    async def before_check_challenge_end(self):
        """Wait until bot is ready before starting the loop"""
        await self.bot.wait_until_ready()

    async def start_photo_collection(self, challenge_id, challenge_name):
        """DM all participants to submit final photos - CONCURRENT VERSION"""
        print(f"📸 [ChallengeEnd] Starting photo collection for challenge {challenge_id}")

        try:
            async with db.pool.acquire() as conn:
                # Get challenge info for notifications
                challenge_info = await conn.fetchrow("""
                    SELECT channel_id FROM challenges WHERE id = $1
                """, challenge_id)

                # Get participants who haven't submitted final photos yet
                participants = await conn.fetch("""
                    SELECT cp.user_id, u.username, COALESCE(cp.submitted_final, FALSE) AS submitted_final,
                           COALESCE(cp.final_dm_sent, FALSE) AS dm_sent
                    FROM challenge_participants cp
                    JOIN users u ON u.user_id = cp.user_id
                    WHERE cp.challenge_id = $1 
                    AND COALESCE(cp.disqualified, FALSE) = FALSE
                    AND COALESCE(cp.submitted_final, FALSE) = FALSE
                """, challenge_id)

                print(f"👥 [ChallengeEnd] Found {len(participants)} participants who need final photo DMs")

                # If no one needs DMs, we're done
                if not participants:
                    print(f"✅ [ChallengeEnd] All participants already submitted or were DMed for challenge {challenge_id}")
                    return

                # Send notification to the challenge channel (only once)
                channel_notified = await conn.fetchval("""
                    SELECT COALESCE(end_notification_sent, FALSE) FROM challenges WHERE id = $1
                """, challenge_id)

                if challenge_info and challenge_info['channel_id'] and not channel_notified:
                    channel = self.bot.get_channel(challenge_info['channel_id'])
                    if channel:
                        # Count total participants for the notification
                        total_participants = await conn.fetchval("""
                            SELECT COUNT(*) FROM challenge_participants 
                            WHERE challenge_id = $1 AND COALESCE(disqualified, FALSE) = FALSE
                        """, challenge_id)

                        pending_count = len(participants)

                        embed = discord.Embed(
                            title=f"🏁 Challenge '{challenge_name}' Has Ended!",
                            description=(
                                f"**📸 Final Photo Submission Phase**\n\n"
                                f"Total participants: **{total_participants}**\n"
                                f"Still need to submit: **{pending_count}**\n"
                                f"⏰ **Deadline:** 24 hours from now\n\n"
                                f"After everyone submits their photos, voting will begin!"
                            ),
                            color=discord.Color.orange()
                        )
                        await channel.send(embed=embed)

                        # Mark channel notification as sent
                        await conn.execute("""
                            UPDATE challenges SET end_notification_sent = TRUE WHERE id = $1
                        """, challenge_id)

                        print(f"📢 [ChallengeEnd] Sent end notification to channel {challenge_info['channel_id']}")

            # Create concurrent tasks for DM sending
            tasks = []
            participants_to_dm = []

            for i, participant in enumerate(participants):
                print(f"\n--- DM DEBUG START ({i + 1}/{len(participants)}) ---")
                print(f"Participant ID: {participant['user_id']}")
                print(f"Username: {participant['username']}")
                print(f"Submitted Final: {participant['submitted_final']}")
                print(f"DM Previously Sent: {participant.get('dm_sent', False)}")

                # Skip if already submitted or already DMed
                if participant['submitted_final'] or participant.get('dm_sent', False):
                    print(f"⏩ [ChallengeEnd] Skipping {participant['username']}, already submitted or DM sent")
                    continue

                # Create task for this participant
                task = asyncio.create_task(
                    self._send_dm_to_participant(participant, challenge_id, challenge_name)
                )
                tasks.append(task)
                participants_to_dm.append(participant)

            if not tasks:
                print("ℹ️ [ChallengeEnd] No participants need DMs")
                return

            print(f"🚀 [ChallengeEnd] Starting {len(tasks)} concurrent DM tasks...")

            # Execute all DM tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update database
            success_count = 0
            fail_count = 0

            async with db.pool.acquire() as conn:
                for i, (result, participant) in enumerate(zip(results, participants_to_dm)):
                    if isinstance(result, Exception):
                        print(f"❌ [ChallengeEnd] Error DMing {participant['username']}: {result}")
                        fail_count += 1

                        # Mark as failed in database
                        try:
                            await conn.execute("""
                                UPDATE challenge_participants 
                                SET final_dm_sent = TRUE, dm_failed = TRUE 
                                WHERE challenge_id = $1 AND user_id = $2
                            """, challenge_id, participant['user_id'])
                        except Exception as db_error:
                            print(f"❌ [ChallengeEnd] Database error marking failed DM: {db_error}")

                    elif result:  # Success
                        print(f"✅ [ChallengeEnd] Successfully sent DM to {participant['username']}")
                        success_count += 1

                        # Mark as sent in database
                        try:
                            await conn.execute("""
                                UPDATE challenge_participants 
                                SET final_dm_sent = TRUE 
                                WHERE challenge_id = $1 AND user_id = $2
                            """, challenge_id, participant['user_id'])

                            # Start reminder task
                            user = await self.bot.fetch_user(participant['user_id'])
                            task_key = f"{challenge_id}_{user.id}"
                            if task_key in self.photo_reminders:
                                self.photo_reminders[task_key].cancel()
                            reminder_task = asyncio.create_task(
                                self.photo_reminder_loop(user, challenge_id, challenge_name)
                            )
                            self.photo_reminders[task_key] = reminder_task

                        except Exception as db_error:
                            print(f"❌ [ChallengeEnd] Database error marking successful DM: {db_error}")
                    else:
                        print(f"⚠️ [ChallengeEnd] Unexpected result for {participant['username']}: {result}")
                        fail_count += 1

                print(f"📊 [ChallengeEnd] DM Summary: {success_count} sent, {fail_count} failed")

                # Check if photo collection should be marked as fully started
                remaining_participants = await conn.fetchval("""
                    SELECT COUNT(*) FROM challenge_participants 
                    WHERE challenge_id = $1 
                    AND COALESCE(disqualified, FALSE) = FALSE
                    AND COALESCE(submitted_final, FALSE) = FALSE
                    AND COALESCE(final_dm_sent, FALSE) = FALSE
                """, challenge_id)

                if remaining_participants == 0:
                    await conn.execute("""
                        UPDATE challenges 
                        SET photo_collection_started = TRUE,
                            photo_collection_deadline = NOW() + INTERVAL '%s hours'
                        WHERE id = $1
                    """ % PHOTO_SUBMISSION_DEADLINE_HOURS, challenge_id)
                    print(f"✅ [ChallengeEnd] All participants processed, photo collection fully started for challenge {challenge_id}")
                else:
                    print(f"⚠️ [ChallengeEnd] {remaining_participants} participants still need DMs for challenge {challenge_id}")

        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in start_photo_collection: {e}")
            traceback.print_exc()

    async def _send_dm_to_participant(self, participant, challenge_id, challenge_name):
        """Helper method to send DM to a single participant"""
        try:
            # Fetch the user
            user = await self.bot.fetch_user(participant['user_id'])
            print(f"✅ [ChallengeEnd] Fetched user: {user} (ID: {user.id})")

            print(f"📩 [ChallengeEnd] Sending DM to {user.name} ({user.id})")

            # Send the DM using the imported function
            await send_final_photo_request(self.bot, user, challenge_id, challenge_name)

            print(f"[ChallengeEnd] DM attempt: {user.name} | success=True | error=''")
            return True

        except discord.NotFound:
            error_msg = f"User {participant['user_id']} not found"
            print(f"[ChallengeEnd] DM attempt: {participant['username']} | success=False | error='{error_msg}'")
            raise discord.NotFound(f"User {participant['user_id']} not found")

        except discord.Forbidden:
            error_msg = f"Cannot DM user {participant['user_id']} - DMs disabled"
            print(f"[ChallengeEnd] DM attempt: {participant['username']} | success=False | error='{error_msg}'")
            raise discord.Forbidden(f"Cannot DM user {participant['user_id']}")

        except Exception as e:
            error_msg = str(e)
            print(f"[ChallengeEnd] DM attempt: {participant['username']} | success=False | error='{error_msg}'")
            print(f"❌ [ChallengeEnd] Failed to DM {participant['username']} ({participant['user_id']}): {e}")
            traceback.print_exc()
            raise e

    async def photo_reminder_loop(self, user, challenge_id, challenge_name):
        """Send periodic reminders to users who haven't submitted photos"""
        try:
            # Wait before starting reminders
            await asyncio.sleep(PHOTO_REMINDER_START_HOURS * 3600)

            reminder_count = 0
            max_reminders = REMINDER_HOURS_THRESHOLD

            while reminder_count < max_reminders:
                # Check if user has submitted
                async with db.pool.acquire() as conn:
                    submitted = await conn.fetchval("""
                        SELECT submitted_final FROM challenge_participants 
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)

                if submitted:
                    print(f"✅ [ChallengeEnd] User {user.name} submitted photos, stopping reminders")
                    break

                # Send reminder
                try:
                    dm = await user.create_dm()
                    await dm.send(
                        f"⏰ **Reminder:** You still need to submit your final photos for **{challenge_name}**!\n"
                        f"Time is running out - please submit as soon as possible."
                    )
                    print(f"📤 [ChallengeEnd] Sent reminder #{reminder_count + 1} to {user.name}")
                except:
                    print(f"❌ [ChallengeEnd] Failed to send reminder to {user.name}")
                    break

                reminder_count += 1
                await asyncio.sleep(PHOTO_REMINDER_INTERVAL_HOURS * 3600)

        except asyncio.CancelledError:
            print(f"🛑 [ChallengeEnd] Reminder task cancelled for {user.name}")
        except Exception as e:
            print(f"❌ [ChallengeEnd] Error in reminder loop for {user.name}: {e}")

    @app_commands.command(name="resend_final_dm",
                          description="Resend final photo DMs to participants who haven't submitted")
    @app_commands.describe(challenge_id="The challenge ID to resend DMs for")
    @app_commands.default_permissions(administrator=True)
    async def resend_final_dm(self, interaction: discord.Interaction, challenge_id: int):
        """Admin command to resend final photo collection DMs"""
        await interaction.response.defer(ephemeral=True)

        try:
            async with db.pool.acquire() as conn:
                # Get challenge details
                challenge = await conn.fetchrow("""
                    SELECT name, status, photo_collection_started 
                    FROM challenges WHERE id = $1
                """, challenge_id)

                if not challenge:
                    await interaction.followup.send(f"❌ Challenge with ID `{challenge_id}` not found!", ephemeral=True)
                    return

                # Reset DM sent flags for participants who haven't submitted
                # This allows them to receive DMs again
                await conn.execute("""
                    UPDATE challenge_participants 
                    SET final_dm_sent = FALSE, dm_failed = FALSE
                    WHERE challenge_id = $1 
                    AND COALESCE(submitted_final, FALSE) = FALSE
                    AND COALESCE(disqualified, FALSE) = FALSE
                """, challenge_id)

                # Get participants who will receive DMs
                participants = await conn.fetch("""
                    SELECT cp.user_id, u.username 
                    FROM challenge_participants cp
                    JOIN users u ON u.user_id = cp.user_id
                    WHERE cp.challenge_id = $1 
                    AND COALESCE(cp.disqualified, FALSE) = FALSE
                    AND COALESCE(cp.submitted_final, FALSE) = FALSE
                """, challenge_id)

            if not participants:
                await interaction.followup.send(
                    f"✅ All participants in **{challenge['name']}** have already submitted their final photos!",
                    ephemeral=True
                )
                return

            # Send initial status
            embed = discord.Embed(
                title="📩 Resending Final Photo DMs",
                description=(
                    f"**Challenge:** {challenge['name']}\n"
                    f"**Participants to DM:** {len(participants)}\n\n"
                    "Triggering photo collection process..."
                ),
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            # Trigger the photo collection process
            await self.start_photo_collection(challenge_id, challenge['name'])

            # Send completion message
            result_embed = discord.Embed(
                title="✅ DM Resend Triggered",
                description=(
                    f"**Challenge:** {challenge['name']}\n\n"
                    f"Photo collection process has been triggered for {len(participants)} participants.\n"
                    "Check the console logs for detailed results."
                ),
                color=discord.Color.green()
            )

            await interaction.edit_original_response(embed=result_embed)

        except Exception as e:
            print(f"❌ [Resend] Command error: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="check_dm_status",
                          description="Check DM status for challenge participants")
    @app_commands.describe(challenge_id="The challenge ID to check")
    @app_commands.default_permissions(administrator=True)
    async def check_dm_status(self, interaction: discord.Interaction, challenge_id: int):
        """Admin command to check DM status for all participants"""
        await interaction.response.defer(ephemeral=True)

        try:
            async with db.pool.acquire() as conn:
                # Get challenge details
                challenge = await conn.fetchrow("""
                        SELECT name, status FROM challenges WHERE id = $1
                    """, challenge_id)

                if not challenge:
                    await interaction.followup.send(f"❌ Challenge with ID `{challenge_id}` not found!", ephemeral=True)
                    return

                # Get all participants with their DM status
                participants = await conn.fetch("""
                        SELECT 
                            cp.user_id, 
                            cp.username,
                            COALESCE(cp.submitted_final, FALSE) AS submitted_final,
                            COALESCE(cp.final_dm_sent, FALSE) AS dm_sent,
                            COALESCE(cp.dm_failed, FALSE) AS dm_failed,
                            COALESCE(cp.disqualified, FALSE) AS disqualified
                        FROM challenge_participants cp
                        WHERE cp.challenge_id = $1
                        ORDER BY cp.username
                    """, challenge_id)

                if not participants:
                    await interaction.followup.send(f"❌ No participants found for challenge {challenge_id}!",
                                                    ephemeral=True)
                    return

                # Create status embed
                embed = discord.Embed(
                    title=f"📊 DM Status for {challenge['name']}",
                    description=f"Challenge ID: {challenge_id}",
                    color=discord.Color.blue()
                )

                # Categorize participants
                submitted = []
                dm_sent_pending = []
                dm_failed = []
                needs_dm = []
                disqualified = []

                for p in participants:
                    if p['disqualified']:
                        disqualified.append(f"• {p['username']}")
                    elif p['submitted_final']:
                        submitted.append(f"• {p['username']}")
                    elif p['dm_failed']:
                        dm_failed.append(f"• {p['username']} (ID: {p['user_id']})")
                    elif p['dm_sent']:
                        dm_sent_pending.append(f"• {p['username']}")
                    else:
                        needs_dm.append(f"• {p['username']} (ID: {p['user_id']})")

                # Add fields
                if submitted:
                    embed.add_field(
                        name=f"✅ Submitted Final Photos ({len(submitted)})",
                        value="\n".join(submitted[:10]) + ("..." if len(submitted) > 10 else ""),
                        inline=False
                    )

                if dm_sent_pending:
                    embed.add_field(
                        name=f"📤 DM Sent, Awaiting Photos ({len(dm_sent_pending)})",
                        value="\n".join(dm_sent_pending[:10]) + ("..." if len(dm_sent_pending) > 10 else ""),
                        inline=False
                    )

                if needs_dm:
                    embed.add_field(
                        name=f"⚠️ Needs DM ({len(needs_dm)})",
                        value="\n".join(needs_dm[:10]) + ("..." if len(needs_dm) > 10 else ""),
                        inline=False
                    )

                if dm_failed:
                    embed.add_field(
                        name=f"❌ DM Failed ({len(dm_failed)})",
                        value="\n".join(dm_failed[:10]) + ("..." if len(dm_failed) > 10 else ""),
                        inline=False
                    )

                if disqualified:
                    embed.add_field(
                        name=f"🚫 Disqualified ({len(disqualified)})",
                        value="\n".join(disqualified[:10]) + ("..." if len(disqualified) > 10 else ""),
                        inline=False
                    )

                embed.set_footer(text="Use /resend_individual_dm to resend to specific users")

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"❌ [DM Status] Command error: {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="resend_individual_dm",
                          description="Resend final photo DM to a specific participant")
    @app_commands.describe(
        challenge_id="The challenge ID",
        user="The user to resend DM to"
    )
    @app_commands.default_permissions(administrator=True)
    async def resend_individual_dm(self, interaction: discord.Interaction, challenge_id: int, user: discord.Member):
        """Admin command to resend final photo collection DM to a specific user"""
        await interaction.response.defer(ephemeral=True)

        try:
            async with db.pool.acquire() as conn:
                # Get challenge details
                challenge = await conn.fetchrow("""
                        SELECT name, status FROM challenges WHERE id = $1
                    """, challenge_id)

                if not challenge:
                    await interaction.followup.send(f"❌ Challenge with ID `{challenge_id}` not found!", ephemeral=True)
                    return

                # Check if user is a participant
                participant = await conn.fetchrow("""
                        SELECT * FROM challenge_participants 
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)

                if not participant:
                    await interaction.followup.send(f"❌ {user.mention} is not a participant in this challenge!",
                                                    ephemeral=True)
                    return

                # Check if they already submitted
                if participant.get('submitted_final'):
                    await interaction.followup.send(f"✅ {user.mention} has already submitted their final photos!",
                                                    ephemeral=True)
                    return

                # Reset DM flags for this specific user
                await conn.execute("""
                        UPDATE challenge_participants 
                        SET final_dm_sent = FALSE, dm_failed = FALSE
                        WHERE challenge_id = $1 AND user_id = $2
                    """, challenge_id, user.id)

            # Send confirmation
            embed = discord.Embed(
                title="📩 Resending Individual DM",
                description=(
                    f"**Challenge:** {challenge['name']}\n"
                    f"**Participant:** {user.mention}\n\n"
                    "Sending final photo DM..."
                ),
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            # Send the DM
            try:
                await self._send_dm_to_participant(
                    {'user_id': user.id, 'username': user.display_name or user.name},
                    challenge_id,
                    challenge['name']
                )

                # Mark as sent in database
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                            UPDATE challenge_participants 
                            SET final_dm_sent = TRUE 
                            WHERE challenge_id = $1 AND user_id = $2
                        """, challenge_id, user.id)

                # Send success message
                success_embed = discord.Embed(
                    title="✅ DM Sent Successfully",
                    description=(
                        f"**Challenge:** {challenge['name']}\n"
                        f"**Participant:** {user.mention}\n\n"
                        "Final photo DM has been sent successfully!"
                    ),
                    color=discord.Color.green()
                )
                await interaction.edit_original_response(embed=success_embed)

            except discord.Forbidden:
                # Update as failed
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                            UPDATE challenge_participants 
                            SET final_dm_sent = TRUE, dm_failed = TRUE 
                            WHERE challenge_id = $1 AND user_id = $2
                        """, challenge_id, user.id)

                error_embed = discord.Embed(
                    title="❌ DM Failed",
                    description=(
                        f"**Challenge:** {challenge['name']}\n"
                        f"**Participant:** {user.mention}\n\n"
                        "❌ Cannot send DM - user has DMs disabled."
                    ),
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=error_embed)

            except Exception as e:
                print(f"❌ [Individual DM] Error sending to {user.name}: {e}")

                error_embed = discord.Embed(
                    title="❌ DM Failed",
                    description=(
                        f"**Challenge:** {challenge['name']}\n"
                        f"**Participant:** {user.mention}\n\n"
                        f"❌ Error: {str(e)}"
                    ),
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=error_embed)

        except Exception as e:
            print(f"❌ [Individual DM] Command error: {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

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
                        # Check if enough participants submitted
                        submission_count = await conn.fetchval("""
                            SELECT COUNT(*) FROM challenge_participants 
                            WHERE challenge_id = $1 
                            AND submitted_final = TRUE 
                            AND COALESCE(disqualified, FALSE) = FALSE
                        """, challenge['id'])

                        if submission_count < 2:
                            print(f"⚠️ [ChallengeEnd] Not enough submissions for voting in {challenge['name']}")
                            # Notify channel
                            channel = self.bot.get_channel(challenge['channel_id'])
                            if channel:
                                await channel.send(
                                    f"⚠️ Challenge **{challenge['name']}** ended with less than 2 submissions. "
                                    f"Voting has been cancelled."
                                )
                            # Mark as completed without voting
                            await conn.execute("""
                                UPDATE challenges 
                                SET status = 'completed', voting_started = TRUE, results_posted = TRUE 
                                WHERE id = $1
                            """, challenge['id'])
                            continue

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

    @check_photo_deadline.before_loop
    async def before_check_photo_deadline(self):
        """Wait until bot is ready before starting the loop"""
        await self.bot.wait_until_ready()

    # Debug command for testing
    @commands.command(name="debug_challenges")
    @commands.has_permissions(administrator=True)
    async def debug_challenges(self, ctx):
        """Debug command to manually check challenge status"""
        await ctx.send("🔍 Manually checking challenge status...")

        # Manually trigger both checks
        await self.check_challenge_end()
        await self.check_photo_deadline()

        # Show current status
        async with db.pool.acquire() as conn:
            active = await conn.fetch("""
                SELECT id, name, photo_collection_started, voting_started 
                FROM challenges WHERE status = 'active'
            """)

            if active:
                status_text = "**Active Challenges:**\n"
                for ch in active:
                    status_text += (
                        f"• {ch['name']} (ID: {ch['id']})\n"
                        f"  Photo Collection: {'✅' if ch['photo_collection_started'] else '❌'}\n"
                        f"  Voting: {'✅' if ch['voting_started'] else '❌'}\n"
                    )
                await ctx.send(status_text)
            else:
                await ctx.send("No active challenges found.")

        await ctx.send("✅ Challenge check completed! Check console for details.")


async def setup(bot):
    await bot.add_cog(ChallengeEnd(bot))