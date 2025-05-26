# commands/challenge.py (Updated with integration)
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

# Set Eastern Time (New York Timezone)
NYC_TZ = pytz.timezone("America/New_York")

class ChallengeDropdown(Select):
    def __init__(self, options):
        super().__init__(placeholder="Select a challenge to join...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        challenge_id = int(self.values[0])
        user_id = interaction.user.id

        print(f"[Join] User {user_id} selected challenge {challenge_id}")

        try:
            async with db.pool.acquire() as conn:
                already = await conn.fetchval("""
                    SELECT COUNT(*) FROM challenge_participants
                    WHERE challenge_id = $1 AND user_id = $2
                """, challenge_id, user_id)

                if already:
                    await interaction.response.send_message("❌ You've already joined this challenge.", ephemeral=True)
                    print(f"[Join] Already joined: user {user_id}")
                    return

                username = interaction.user.display_name or interaction.user.name

                await conn.execute("""
                    INSERT INTO challenge_participants (challenge_id, user_id, username)
                    VALUES ($1, $2, $3)
                """, challenge_id, user_id, username)

            try:
                user = await interaction.client.fetch_user(user_id)
                dm = await user.create_dm()

                embed = discord.Embed(
                    title="📸 Welcome to the Challenge!",
                    description=(
                        "**Please upload your 4 initial photos** in these poses:\n\n"
                        "1️⃣ Relaxed Front Pose\n"
                        "2️⃣ Front Double Biceps\n"
                        "3️⃣ Rear Double Biceps\n"
                        "4️⃣ Relaxed Back Pose\n\n"
                        "⏰ You can send all at once or one at a time. Type 'done' when finished.\n"
                    ),
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Reply to this DM to begin.")
                await dm.send(embed=embed)

                # Send examples
                example_photos = [
                    "assets/example.png", "assets/example1.png",
                    "assets/example2.png", "assets/example3.png"
                ]
                for photo in example_photos:
                    if os.path.exists(photo):
                        await dm.send(file=discord.File(photo))

                # Ask for photos
                await dm.send("📸 Upload your 4 initial photos now. Type 'done' when you're finished.")

                def photo_check(m):
                    return m.author.id == user_id and m.channel == dm

                photos = []
                while len(photos) < 4:
                    msg = await interaction.client.wait_for("message", check=photo_check, timeout=600)
                    if msg.content.lower() == "done":
                        break
                    for attachment in msg.attachments:
                        if len(photos) < 4:
                            photo_path = f"challenge/{challenge_id}/initial/{user_id}"
                            os.makedirs(photo_path, exist_ok=True)
                            file_path = os.path.join(photo_path, f"photo_{len(photos) + 1}_{attachment.filename}")
                            await attachment.save(file_path)
                            photos.append(file_path)
                    await dm.send(f"✅ Received {len(photos)}/4 photos.")

                # Ask for weight
                await dm.send("⚖️ What is your **current weight** in pounds?")
                weight_msg = await interaction.client.wait_for("message", check=photo_check, timeout=300)
                current_weight = float(weight_msg.content.strip())

                await dm.send("🎯 What is your **goal weight**?")
                goal_weight_msg = await interaction.client.wait_for("message", check=photo_check, timeout=300)
                goal_weight = float(goal_weight_msg.content.strip())

                await dm.send("💬 What is your **personal goal** for this challenge?")
                goal_msg = await interaction.client.wait_for("message", check=photo_check, timeout=300)
                personal_goal = goal_msg.content.strip()

                # Update DB
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE challenge_participants
                        SET current_weight = $1,
                            goal_weight = $2,
                            personal_goal = $3,
                            initial_photos = $4
                        WHERE challenge_id = $5 AND user_id = $6
                    """, current_weight, goal_weight, personal_goal, photos, challenge_id, user_id)

                await dm.send("✅ You're fully registered for the challenge. Good luck! 💪")

            except Exception as e:
                print(f"❌ DM process failed for user {user_id}: {e}")

            await interaction.response.send_message("✅ You’ve joined the challenge!", ephemeral=True)
            print(f"[Join] Success: user {user_id} joined challenge {challenge_id}")

        except Exception as e:
            print(f"❌ [Join] Error joining challenge: {e}")
            try:
                await interaction.response.send_message("⚠️ An error occurred while trying to join.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("⚠️ An error occurred after selection.", ephemeral=True)


class ChallengeSelectView(View):
    def __init__(self, options):
        super().__init__(timeout=60)
        self.add_item(ChallengeDropdown(options))

class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize sub-components
        self.challenge_end = ChallengeEnd(bot)
        self.challenge_voting = ChallengeVoting(bot)

    @app_commands.command(name="challenge", description="Start a new challenge!")
    @app_commands.describe(
        days="Duration of the challenge in days",
        name="Name of the challenge",
        goal="Description of the challenge goal"
    )
    async def challenge(self, interaction: discord.Interaction, days: int, name: str, goal: str):
        """Start a new fitness challenge"""
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can start challenges!", ephemeral=True)
            return

        # For testing: allow any duration
        if days <= 0:
            await interaction.response.send_message("❌ Duration must be at least 1 minute (0.0007 days)!",
                                                    ephemeral=True)
            return

        if len(name) > 50:
            await interaction.response.send_message("❌ Challenge name must be 50 characters or less!", ephemeral=True)
            return

        await interaction.response.defer()

        # Note: Multiple challenges allowed
        print(f"{interaction.user.name} is creating a challenge: {name}")

        # Create challenge (rest of existing code...)
        start_date = datetime.now(NYC_TZ).replace(tzinfo=None)
        end_date = (datetime.now(NYC_TZ) + timedelta(days=days)).replace(tzinfo=None)

        # Optional: show seconds/minutes if <1 day for clarity in embed
        duration_str = (
            f"{int(days * 24 * 60)} minutes"
            if days < 1 else f"{days} Days"
        )

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
                    f"📅 **Duration:** {duration_str}\\n"
                    f"🕒 **Start Date:** {start_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                    f"🛑 **End Date:** {end_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                    f"🎯 **Goal:** {goal}\n\n"
                    f"**📸 Requirements:**\n"
                    f"• Submit 4 initial photos (specific poses)\n"
                    f"• Track your weight progress\n"
                    f"• Submit 4 final photos at the end\n"
                    f"• Community voting determines winners!\n\n"
                    f"✅ **React to Join!**"
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
        async with db.pool.acquire() as conn:
            challenge = await conn.fetchrow("""
                SELECT * FROM challenges WHERE status = 'active' ORDER BY start_date DESC LIMIT 1
            """)

            if not challenge:
                await interaction.response.send_message("⚠️ No active challenge found!", ephemeral=True)
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
            embed.add_field(name="⏰ Time Remaining", value=f"{time_remaining.days} days", inline=True)

            status = "📸 Collecting Photos" if challenge['photo_collection_started'] else "🟢 Active"
            if challenge['voting_started']:
                status = "🗳️ Voting in Progress"
            elif challenge['results_posted']:
                status = "✅ Completed"

            embed.add_field(name="📌 Status", value=status, inline=True)

            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="my_challenge_progress", description="View your challenge progress")
    async def my_challenge_progress(self, interaction: discord.Interaction):
        """Show user's personal challenge progress"""
        user_id = interaction.user.id

        async with db.pool.acquire() as conn:
            # Get active challenge
            challenge = await conn.fetchrow("""
                SELECT id, name FROM challenges WHERE status = 'active' ORDER BY start_date DESC LIMIT 1
            """)

            if not challenge:
                await interaction.response.send_message("⚠️ No active challenge found!", ephemeral=True)
                return

            # Get user's participation data
            participant = await conn.fetchrow("""
                SELECT * FROM challenge_participants 
                WHERE challenge_id = $1 AND user_id = $2
            """, challenge['id'], user_id)

            if not participant:
                await interaction.response.send_message("❌ You are not participating in the current challenge!",
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
            photo_status = "✅ Submitted" if participant['submitted_final'] else "❌ Not yet submitted"
            embed.add_field(name="📸 Final Photos", value=photo_status, inline=True)

            # Add tips
            if not participant['submitted_final'] and challenge['photo_collection_started']:
                embed.add_field(
                    name="⚠️ Action Required",
                    value="Final photos collection has started! Check your DMs.",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="join_challenge", description="Join a specific fitness challenge")
    async def join_challenge(self, interaction: discord.Interaction):
        """Allow a user to choose which active challenge to join."""

        async with db.pool.acquire() as conn:
            active = await conn.fetch("""
                SELECT id, name, end_date FROM challenges 
                WHERE status = 'active'
                ORDER BY start_date DESC
            """)

        if not active:
            await interaction.response.send_message("⚠️ No active challenges found.", ephemeral=True)
            return

        # Build select menu options
        options = [
            discord.SelectOption(
                label=challenge["name"],
                description=f"Ends {challenge['end_date'].strftime('%b %d')}",
                value=str(challenge["id"])
            )
            for challenge in active
        ]

        view = ChallengeSelectView(options)
        await interaction.response.send_message("👇 Choose which challenge to join:", view=view, ephemeral=True)

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

            # Try to DM user
            try:
                dm = await user.create_dm()
                embed = discord.Embed(
                    title="📸 Welcome to the Challenge!",
                    description=(
                        "**Please upload your 4 initial photos** in these poses:\n\n"
                        "1️⃣ Relaxed Front Pose\n"
                        "2️⃣ Front Double Biceps\n"
                        "3️⃣ Rear Double Biceps\n"
                        "4️⃣ Relaxed Back Pose\n\n"
                        "⏰ You can send all at once or one at a time. Type 'done' when finished."
                    ),
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Reply to this DM to begin.")
                await dm.send(embed=embed)

                example_photos = [
                    "assets/example.png", "assets/example1.png",
                    "assets/example2.png", "assets/example3.png"
                ]
                for photo in example_photos:
                    if os.path.exists(photo):
                        await dm.send(file=discord.File(photo))

                await dm.send("📸 Upload your 4 initial photos now. Type 'done' when you're finished.")

                print(f"📬 DM onboarding sent to {user.name} ({user.id})")

            except Exception as e:
                print(f"❌ Failed to DM user {user.id}: {e}")

            # ✅ Notify in public channel
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                await channel.send(
                    f"<@{payload.user_id}> ✅ We’ve sent you a DM to get started.\n"
                    f"If you don’t see it, use the `/join_challenge` command to join manually."
                )

async def setup(bot):
    await bot.add_cog(Challenge(bot))