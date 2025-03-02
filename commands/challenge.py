import discord
import os
import asyncio
import uuid
import pytz
from discord import app_commands
from discord.ext import commands, tasks
from database import db
from datetime import datetime, timedelta

# Set Eastern Time (New York Timezone)
NYC_TZ = pytz.timezone("America/New_York")

VOTING_CHANNEL_ID = 1235378047390187601  # Replace with actual channel ID

class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="challenge", description="Start a new challenge!")
    async def challenge(self, interaction: discord.Interaction, days: int, name: str, goal: str):
        print("[DEBUG] Received /challenge start command")

        await interaction.response.defer()
        print("[DEBUG] Interaction response deferred.")

        # Ensure all timestamps are naive before inserting into PostgreSQL
        start_date = datetime.now(NYC_TZ).replace(tzinfo=None)  # Remove timezone info
        end_date = (datetime.now(NYC_TZ) + timedelta(days=days)).replace(tzinfo=None)

        print(f"[DEBUG] Challenge start date set to (naive): {start_date}")
        print(f"[DEBUG] Challenge end date set to (naive): {end_date}")

        try:
            print("[DEBUG] Challenge date calculation successful.")
            async with db.pool.acquire() as conn:
                print("[DEBUG] Acquired database connection.")
                await conn.execute(
                    """
                    INSERT INTO challenges (name, goal, start_date, end_date, status)
                    VALUES ($1, $2, $3, $4, 'active')
                    """, name, goal, start_date, end_date
                )
                print("[DEBUG] Challenge successfully inserted into database.")
                challenge_id = await conn.fetchval(
                    "SELECT id FROM challenges WHERE name = $1 ORDER BY start_date DESC LIMIT 1",
                    name
                )
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            return

        # Create challenge announcement message
        embed = discord.Embed(
            title=f"🏆 New Challenge: {name}",
            description=(
                f"📅 **Duration:** {days} Days\n"
                f"🕒 **Start Date:** {start_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                f"🛑 **End Date:** {end_date.strftime('%Y-%m-%d %I:%M %p')}\n"
                f"🎯 **Goal:** {goal}\n"
                f"✅ **React to Join!**"
            ),
            color=discord.Color.gold()
        )

        try:
            challenge_message = await interaction.channel.send(embed=embed)
            print("[DEBUG] Challenge message sent.")
            await challenge_message.add_reaction("✅")
            print("[DEBUG] Reaction added to challenge message.")
            await interaction.followup.send("✅ Challenge created successfully! Users can now join.", ephemeral=True)

            # Store message ID and channel ID in the database
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE challenges SET message_id = $1, channel_id = $2 WHERE id = $3
                """, challenge_message.id, interaction.channel.id, challenge_id)

            # Start listening for reactions
            await self.wait_for_reactions(challenge_id)

        except Exception as e:
            print(f"[ERROR] Failed to send challenge message: {e}")
            await interaction.followup.send("❌ Error sending challenge message.", ephemeral=True)

    async def wait_for_reactions(self, challenge_id):
        """Continues waiting for reactions on restart."""
        print(f"[DEBUG] Resuming reaction listener for active challenge: {challenge_id}")

        async with db.pool.acquire() as conn:
            challenge_data = await conn.fetchrow("""
                SELECT message_id, channel_id FROM challenges WHERE id = $1
            """, challenge_id)

        if not challenge_data:
            print("[WARNING] No challenge data found for ID:", challenge_id)
            return

        message_id = challenge_data["message_id"]
        channel_id = challenge_data["channel_id"]

        print(f"[DEBUG] Retrieved message_id: {message_id}, channel_id: {channel_id}")
        if not message_id or not channel_id:
            print("[ERROR] No message ID or channel ID found for challenge.")
            return

        print("[DEBUG] Checking if bot can access channel...")
        channel = self.bot.get_channel(channel_id)

        if not channel:
            print(f"[ERROR] Could not find channel with ID {channel_id}. Check if bot has access!")
            return

        try:
            await asyncio.sleep(2)
            challenge_message = await channel.fetch_message(message_id)
            print(f"[DEBUG] ✅ Successfully fetched challenge message {challenge_message.id}")
        except discord.NotFound:
            print("[WARNING] Challenge message not found.")
            return
        except discord.Forbidden:
            print("[ERROR] ❌ Bot does not have permission to read messages in this channel!")
            return

        def check(reaction, user):
            """Log every reaction event to confirm Discord is sending them."""
            print(f"[DEBUG] 🔄 Reaction detected: {reaction.emoji} from {user.name} on message {reaction.message.id}")

            if user.bot:
                print(f"[DEBUG] Ignoring bot reaction from {user.name}")
                return False

            if reaction.message.id != message_id:
                print(f"[WARNING] Reaction on the wrong message. Expected {message_id}, got {reaction.message.id}")
                return False

            return str(reaction.emoji) == "✅"

        print("[DEBUG] Waiting for reactions...")
        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=86400, check=check)
                print(f"[DEBUG] User {user.name} reacted with {reaction.emoji}")

                # **DEBUG LOG BEFORE DATABASE INSERT**
                print(
                    f"[DEBUG] Inserting user {user.name} (ID: {user.id}) into challenge_participants for challenge {challenge_id}")

                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO challenge_participants (challenge_id, user_id, username)
                        VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """, challenge_id, user.id, user.name)

                print(
                    f"[DEBUG] Successfully inserted {user.name} into challenge_participants.")  # ✅ Ensure it was added

                # **Trigger DM process**
                print(f"[DEBUG] Registering user: {user.name}")  # ✅ Confirm before DM is sent
                await self.register_user(user)

            except asyncio.TimeoutError:
                print("[DEBUG] Challenge reaction collection ended.")
                break  # Stop waiting

    async def check_challenge_end(self):
        """Checks if challenges have ended and updates status."""
        async with db.pool.acquire() as conn:
            challenges = await conn.fetch("""
                SELECT id FROM challenges WHERE end_date <= NOW() AND status = 'active'
            """)

            for challenge in challenges:
                print(f"[DEBUG] Marking challenge {challenge['id']} as completed.")
                await conn.execute("""
                    UPDATE challenges SET status = 'completed' WHERE id = $1
                """, challenge["id"])

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handles reactions across servers, even for uncached messages."""
        if payload.emoji.name != "✅":
            return  # Ignore non-checkmark reactions

        user = self.bot.get_user(payload.user_id)
        if user is None or user.bot:
            return  # Ignore bots

        async with db.pool.acquire() as conn:
            challenge = await conn.fetchrow("""
                SELECT id, message_id, channel_id FROM challenges 
                WHERE message_id = $1
            """, payload.message_id)

        if not challenge:
            print(f"[WARNING] Reaction not linked to an active challenge (Message ID: {payload.message_id})")
            return

        challenge_id = challenge["id"]

        # ✅ Start DM registration process
        print(f"[DEBUG] ✅ Reaction linked to challenge ID: {challenge_id} by {user.name}")
        await self.register_user(user, challenge_id)

    async def register_user(self, user, challenge_id):
        """Registers a user in the challenge_participants table and asks for weight/goal/photos."""
        print(f"[DEBUG] Sending registration DM to {user.name}")

        try:
            dm_channel = await user.create_dm()
            await dm_channel.send("🏆 Welcome to the challenge! Let's get started.")

            # Ask for weight
            await dm_channel.send("⚖️ Please enter your current weight:")
            msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel,
                                          timeout=120)
            current_weight = float(msg.content)

            # Ask for goal weight
            await dm_channel.send("🎯 Please enter your goal weight:")
            msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel,
                                          timeout=120)
            goal_weight = float(msg.content)

            # Ask for personal goal
            await dm_channel.send("✍️ What is your personal goal? (e.g., 'Lose 10 lbs', 'Bulk up', 'Main Gain')")
            msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel,
                                          timeout=120)
            personal_goal = msg.content

            # Generate a unique folder using UUID
            user_uuid = str(uuid.uuid4())
            user_folder = os.path.join("challenge", user_uuid)  # Save inside challenge/uuid/
            os.makedirs(user_folder, exist_ok=True)

            # Show example photos and ask for initial photos
            await dm_channel.send(
                "📸 Please upload 4 photos following the example poses: Relaxed Front Pose, Front Double Biceps, Rear Double Biceps, and Relaxed Back Pose.")
            example_photos = ["assets/example.png", "assets/example1.png", "assets/example2.png", "assets/example3.png"]
            await dm_channel.send(files=[discord.File(photo) for photo in example_photos])

            photos = []
            while len(photos) < 4:
                msg = await self.bot.wait_for("message", check=lambda
                    m: m.author == user and m.channel == dm_channel and m.attachments, timeout=300)
                for attachment in msg.attachments:
                    photo_path = os.path.join(user_folder, attachment.filename)
                    await attachment.save(photo_path)
                    photos.append(photo_path)

            await dm_channel.send(
                "✅ Photos received! Would you like to upload any additional poses? Send them now or type 'done'.")

            while True:
                msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel,
                                              timeout=300)
                if msg.content.lower() == "done":
                    break
                if msg.attachments:
                    for attachment in msg.attachments:
                        photo_path = os.path.join(user_folder, attachment.filename)
                        await attachment.save(photo_path)
                        photos.append(photo_path)

            # Store user details in database AFTER completing registration
            try:
                async with db.pool.acquire() as conn:
                    print(f"[DEBUG] Registering {user.name} in challenge_participants.")
                    await conn.execute("""
                        INSERT INTO challenge_participants (challenge_id, user_id, username, current_weight, goal_weight, personal_goal, initial_photos)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, challenge_id, user.id, user.name, current_weight, goal_weight, personal_goal, photos)
                    print("[DEBUG] Successfully registered participant.")
                    await dm_channel.send("✅ You have been successfully registered in the challenge!")
            except Exception as e:
                print(f"[ERROR] Failed to register participant: {e}")
                await dm_channel.send("❌ Error joining the challenge.")
                return

        except discord.Forbidden:
            print(f"[ERROR] Cannot send DM to {user.name}. They may have DMs disabled.")
        except asyncio.TimeoutError:
            print(f"[WARNING] {user.name} did not respond in time.")
            await dm_channel.send("⏳ Registration timed out. Please react again to restart.")
        except Exception as e:
            print(f"[ERROR] Unexpected error in register_user: {e}")

async def setup(bot):
    """Registers the Challenge cog when the bot starts."""
    await bot.add_cog(Challenge(bot))
