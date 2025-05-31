# commands/challenge.py (Fixed version that properly handles Discord interactions)
import discord
import os
import asyncio
import uuid
import pytz
from discord import app_commands
from discord.ui import View, Select
from discord.ext import commands, tasks
from database import db
from datetime import datetime, timedelta
from .challenge_end import ChallengeEnd
from .challenge_voting import ChallengeVoting
from utils.shared import send_final_photo_request

# Set Eastern Time (New York Timezone)
NYC_TZ = pytz.timezone("America/New_York")


class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize sub-components
        self.challenge_end = ChallengeEnd(bot)
        self.challenge_voting = ChallengeVoting(bot)

    def parse_duration(self, duration_str):
        """Parse duration string like '30m', '2h', '5d' and return (value, unit, total_minutes)"""
        duration_str = duration_str.lower().strip()

        if duration_str[-1] not in ['m', 'h', 'd']:
            raise ValueError(
                "Duration must end with 'm' (minutes), 'h' (hours), or 'd' (days). Example: '30m', '2h', '5d'")

        try:
            value = int(duration_str[:-1])
            unit = duration_str[-1]
        except ValueError:
            raise ValueError(
                "Invalid duration format. Use numbers followed by 'm', 'h', or 'd'. Example: '30m', '2h', '5d'")

        if value <= 0:
            raise ValueError("Duration must be greater than 0")

        # Convert to total minutes
        if unit == 'm':
            total_minutes = value
        elif unit == 'h':
            total_minutes = value * 60
        elif unit == 'd':
            total_minutes = value * 60 * 24

        return value, unit, total_minutes

    def format_duration_display(self, value, unit):
        """Format duration for display with proper singular/plural"""
        if unit == 'm':
            return f"{value} Minute{'s' if value != 1 else ''}"
        elif unit == 'h':
            return f"{value} Hour{'s' if value != 1 else ''}"
        elif unit == 'd':
            return f"{value} Day{'s' if value != 1 else ''}"

    @app_commands.command(name="challenge", description="Start a new challenge!")
    @app_commands.describe(
        duration="Duration of the challenge (use 'm' for minutes, 'h' for hours, 'd' for days, e.g., '30m', '2h', '5d')",
        name="Name of the challenge",
        goal="Description of the challenge goal"
    )
    async def challenge(self, interaction: discord.Interaction, duration: str, name: str, goal: str):
        """Start a new fitness challenge"""
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can start challenges!", ephemeral=True)
            return

        # Parse duration string - this must happen BEFORE defer()
        try:
            duration_value, duration_unit, total_minutes = self.parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
            return

        if len(name) > 50:
            await interaction.response.send_message("❌ Challenge name must be 50 characters or less!", ephemeral=True)
            return

        # IMPORTANT: Must defer() early to prevent timeout
        await interaction.response.defer()

        print(f"{interaction.user.name} is creating a challenge: {name}")

        # Create challenge
        start_date = datetime.now(NYC_TZ).replace(tzinfo=None)
        end_date = (datetime.now(NYC_TZ) + timedelta(minutes=total_minutes)).replace(tzinfo=None)

        # Create proper duration string
        duration_str = self.format_duration_display(duration_value, duration_unit)

        try:
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO challenges (name, goal, start_date, end_date, status)
                    VALUES ($1, $2, $3, $4, 'active')
                """, name, goal, start_date, end_date)

                challenge_id = await conn.fetchval(
                    "SELECT id FROM challenges WHERE name = $1 ORDER BY start_date DESC LIMIT 1",
                    name
                )

            # Create enhanced challenge announcement
            embed = discord.Embed(
                title=f"🏆 New Challenge: {name}",
                description=(
                    f"📅 **Duration:** {duration_str}\n"
                    f"🕒 **Start Date:** {start_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                    f"🛑 **End Date:** {end_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                    f"🎯 **Goal:** {goal}\n\n"
                    f"**📸 Requirements:**\n"
                    f"• Submit 4 initial photos (specific poses)\n"
                    f"• Track your weight progress\n"
                    f"• Submit 4 final photos at the end\n"
                    f"• Community voting determines winners!\n\n"
                    f"✅ **React with ✅ to Join!**"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="Good luck to all participants! 💪")

            challenge_message = await interaction.channel.send(embed=embed)
            await challenge_message.add_reaction("✅")
            await interaction.followup.send("✅ Challenge created successfully!", ephemeral=True)

            # Store message ID and channel ID
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE challenges SET message_id = $1, channel_id = $2 WHERE id = $3
                """, challenge_message.id, interaction.channel.id, challenge_id)

        except Exception as e:
            await interaction.followup.send(f"❌ Error creating challenge: {e}", ephemeral=True)

    @app_commands.command(name="challenge_status", description="Check the current challenge status")
    async def challenge_status(self, interaction: discord.Interaction):
        """Display detailed information about the active challenge"""
        await interaction.response.defer()  # Prevent timeout

        async with db.pool.acquire() as conn:
            challenge = await conn.fetchrow("""
                SELECT * FROM challenges WHERE status = 'active' ORDER BY start_date DESC LIMIT 1
            """)

            if not challenge:
                await interaction.followup.send("⚠️ No active challenge found!", ephemeral=True)
                return

            # Get participant count
            participant_count = await conn.fetchval("""
                SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = $1
            """, challenge['id'])

            # Calculate time remaining
            end_date = challenge['end_date']
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            time_remaining = end_date - datetime.now()

            # Create status embed
            embed = discord.Embed(
                title=f"📊 Challenge Status: {challenge['name']}",
                color=discord.Color.blue()
            )

            embed.add_field(name="🎯 Goal", value=challenge['goal'], inline=False)
            embed.add_field(name="👥 Participants", value=str(participant_count), inline=True)

            # Better time remaining display
            if time_remaining.total_seconds() > 0:
                if time_remaining.days > 0:
                    time_str = f"{time_remaining.days} day{'s' if time_remaining.days != 1 else ''}"
                elif time_remaining.seconds > 3600:
                    hours = time_remaining.seconds // 3600
                    time_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = time_remaining.seconds // 60
                    time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                time_str = "Ended"

            embed.add_field(name="⏰ Time Remaining", value=time_str, inline=True)

            status = "📸 Collecting Photos" if challenge.get('photo_collection_started') else "🟢 Active"
            if challenge.get('voting_started'):
                status = "🗳️ Voting in Progress"
            elif challenge.get('results_posted'):
                status = "✅ Completed"

            embed.add_field(name="📌 Status", value=status, inline=True)

            await interaction.followup.send(embed=embed)

    @app_commands.command(name="my_challenge_progress", description="View your challenge progress")
    async def my_challenge_progress(self, interaction: discord.Interaction):
        """Show user's personal challenge progress"""
        await interaction.response.defer(ephemeral=True)  # Make it ephemeral

        user_id = interaction.user.id

        async with db.pool.acquire() as conn:
            # Get active challenge
            challenge = await conn.fetchrow("""
                SELECT id, name FROM challenges WHERE status = 'active' ORDER BY start_date DESC LIMIT 1
            """)

            if not challenge:
                await interaction.followup.send("⚠️ No active challenge found!", ephemeral=True)
                return

            # Get user's participation data
            participant = await conn.fetchrow("""
                SELECT * FROM challenge_participants 
                WHERE challenge_id = $1 AND user_id = $2
            """, challenge['id'], user_id)

            if not participant:
                await interaction.followup.send("❌ You are not participating in the current challenge!",
                                                ephemeral=True)
                return

            # Create progress embed
            embed = discord.Embed(
                title=f"📈 Your Progress in {challenge['name']}",
                color=discord.Color.green()
            )

            # Weight progress
            weight_change = 0
            if participant['final_weight']:
                weight_change = participant['final_weight'] - participant['current_weight']
            elif participant['current_weight']:
                # Get latest weight from check-ins
                latest_weight = await conn.fetchval("""
                    SELECT weight FROM checkins 
                    WHERE user_id = $1 AND category = 'weight' 
                    ORDER BY timestamp DESC LIMIT 1
                """, user_id)
                if latest_weight:
                    weight_change = latest_weight - participant['current_weight']

            embed.add_field(
                name="⚖️ Weight Progress",
                value=(
                    f"**Starting:** {participant['current_weight']} lbs\n"
                    f"**Goal:** {participant['goal_weight']} lbs\n"
                    f"**Current Change:** {weight_change:+.1f} lbs"
                ),
                inline=False
            )

            embed.add_field(
                name="🎯 Personal Goal",
                value=participant['personal_goal'] or "Not set",
                inline=False
            )

            # Photo status
            photo_status = "✅ Submitted" if participant.get('submitted_final') else "❌ Not yet submitted"
            embed.add_field(name="📸 Final Photos", value=photo_status, inline=True)

            # Add tips
            if not participant.get('submitted_final') and challenge.get('photo_collection_started'):
                embed.add_field(
                    name="⚠️ Action Required",
                    value="Final photos collection has started! Check your DMs.",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        print(
            f"[Reaction Debug] ✅ Detected reaction '{payload.emoji.name}' on message {payload.message_id} from user {payload.user_id}")

        if payload.emoji.name != "✅":
            return

        if payload.user_id == self.bot.user.id:
            return

        async with db.pool.acquire() as conn:
            challenge = await conn.fetchrow("""
                SELECT id, name FROM challenges 
                WHERE message_id = $1 AND status = 'active'
            """, payload.message_id)

            if not challenge:
                return

            already_joined = await conn.fetchval("""
                SELECT COUNT(*) FROM challenge_participants 
                WHERE challenge_id = $1 AND user_id = $2
            """, challenge['id'], payload.user_id)

            if already_joined:
                # Send ephemeral-style message by DMing the user
                try:
                    user = await self.bot.fetch_user(payload.user_id)
                    dm = await user.create_dm()
                    await dm.send("❌ You've already joined this challenge!")
                except:
                    pass
                return

            user = await self.bot.fetch_user(payload.user_id)
            if not user:
                print(f"⚠️ Could not fetch user {payload.user_id}")
                return

            username = user.display_name or user.name

            await conn.execute("""
                INSERT INTO challenge_participants (challenge_id, user_id, username)
                VALUES ($1, $2, $3)
            """, challenge['id'], payload.user_id, username)

            # Start the sequential DM onboarding process
            await self.start_sequential_dm_onboarding(challenge['id'], challenge['name'], user)

            # ✅ Notify in public channel
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                await channel.send(
                    f"<@{payload.user_id}> ✅ We've sent you a DM to get started with your initial photos!"
                )

    async def start_sequential_dm_onboarding(self, challenge_id, challenge_name, user):
        """Handle the complete DM onboarding process with sequential photo collection"""
        try:
            dm = await user.create_dm()

            embed = discord.Embed(
                title=f"📸 Welcome to {challenge_name}!",
                description=(
                    "**Please upload your 4 initial photos** in these poses:\n\n"
                    "1️⃣ Relaxed Front Pose\n"
                    "2️⃣ Front Double Biceps\n"
                    "3️⃣ Rear Double Biceps\n"
                    "4️⃣ Relaxed Back Pose\n\n"
                    "📋 **Process:** I'll show you an example, then you upload your version. We'll do this for all 4 poses.\n"
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="Let's start with the first pose!")
            await dm.send(embed=embed)

            def photo_check(m):
                return m.author.id == user.id and m.channel == dm and m.attachments

            photos = []

            # Example photos and their corresponding pose instructions
            example_data = [
                {
                    "file": "assets/example.png",
                    "pose": "Relaxed Front Pose",
                    "instruction": "📸 Now upload your **Relaxed Front Pose** photo:"
                },
                {
                    "file": "assets/example1.png",
                    "pose": "Front Double Biceps",
                    "instruction": "📸 Now upload your **Front Double Biceps** photo:"
                },
                {
                    "file": "assets/example2.png",
                    "pose": "Rear Double Biceps",
                    "instruction": "📸 Now upload your **Rear Double Biceps** photo:"
                },
                {
                    "file": "assets/example3.png",
                    "pose": "Relaxed Back Pose",
                    "instruction": "📸 Now upload your **Relaxed Back Pose** photo:"
                }
            ]

            # Sequential photo collection
            for i, data in enumerate(example_data):
                # Show example photo
                if os.path.exists(data["file"]):
                    await dm.send(f"**{i + 1}️⃣ Example: {data['pose']}**")
                    await dm.send(file=discord.File(data["file"]))

                # Ask for user's photo
                await dm.send(data["instruction"])

                # Wait for user photo (no timeout)
                msg = await self.bot.wait_for("message", check=photo_check)

                # Save the photo
                attachment = msg.attachments[0]
                photo_path = f"challenge/{challenge_id}/initial/{user.id}"
                os.makedirs(photo_path, exist_ok=True)
                file_path = os.path.join(photo_path, f"photo_{i + 1}_{attachment.filename}")
                await attachment.save(file_path)
                photos.append(file_path)

                await dm.send(f"✅ Photo {i + 1}/4 received! Great job!")

                # Small delay before next pose
                if i < len(example_data) - 1:
                    await asyncio.sleep(1)
                    await dm.send("━" * 30)

            await dm.send("🎉 All initial photos received! Now let's get your weight and goals...")

            # Ask for weight
            await dm.send("⚖️ What is your **current weight** in pounds? (e.g., 175.5)")

            def text_check(m):
                return m.author.id == user.id and m.channel == dm and not m.attachments

            weight_msg = await self.bot.wait_for("message", check=text_check, timeout=300)
            current_weight = float(weight_msg.content.strip())

            await dm.send("🎯 What is your **goal weight** in pounds?")
            goal_weight_msg = await self.bot.wait_for("message", check=text_check, timeout=300)
            goal_weight = float(goal_weight_msg.content.strip())

            await dm.send("💬 What is your **personal goal** for this challenge? (e.g., 'Lose 10 lbs and build muscle')")
            goal_msg = await self.bot.wait_for("message", check=text_check, timeout=300)
            personal_goal = goal_msg.content.strip()

            # Update DB with all collected data
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE challenge_participants
                    SET current_weight = $1,
                        goal_weight = $2,
                        personal_goal = $3,
                        initial_photos = $4
                    WHERE challenge_id = $5 AND user_id = $6
                """, current_weight, goal_weight, personal_goal, photos, challenge_id, user.id)

            # Final confirmation
            embed = discord.Embed(
                title="✅ Registration Complete!",
                description=(
                    f"You're now fully registered for **{challenge_name}**!\n\n"
                    f"📊 **Your Details:**\n"
                    f"• Starting Weight: {current_weight} lbs\n"
                    f"• Goal Weight: {goal_weight} lbs\n"
                    f"• Personal Goal: {personal_goal}\n"
                    f"• Photos: {len(photos)} submitted\n\n"
                    f"💪 Good luck with your fitness journey!"
                ),
                color=discord.Color.green()
            )
            await dm.send(embed=embed)

        except asyncio.TimeoutError:
            await dm.send("⏰ Registration timed out. React to the challenge message again to restart.")
        except ValueError:
            await dm.send("❌ Invalid weight format. Please react to the challenge message again to restart.")
        except Exception as e:
            print(f"❌ DM process failed for user {user.id}: {e}")
            await dm.send("❌ Something went wrong during registration. Please react to the challenge message again.")


async def setup(bot):
    await bot.add_cog(Challenge(bot))