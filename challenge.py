import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from database import db


class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_challenge = None  # Store active challenge info

    @app_commands.command(name="challenge", description="Start a new challenge!")
    async def challenge(self, interaction: discord.Interaction, days: int, message: str):
        if self.active_challenge:
            await interaction.response.send_message(
                "⚠️ A challenge is already active! Wait for it to finish before starting a new one.", ephemeral=True)
            return

        end_date = discord.utils.utcnow() + discord.utils.timedelta(days=days)

        # Store challenge details in DB
        async with db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO challenges (user_id, username, start_date, end_date, status)
                VALUES ($1, $2, NOW(), $3, 'active')
            """, interaction.user.id, interaction.user.name, end_date)

        self.active_challenge = {
            "message": message,
            "end_date": end_date,
            "participants": []
        }

        # Send challenge message
        embed = discord.Embed(
            title="🏆 New Challenge Started!",
            description=f"📅 **Duration:** {days} Days\n📢 **Goal:** {message}\n✅ **React to Join!**",
            color=discord.Color.gold()
        )

        challenge_message = await interaction.channel.send(embed=embed)
        await challenge_message.add_reaction("✅")
        await interaction.response.send_message("✅ Challenge created successfully! Users can now join.", ephemeral=True)

        # Wait for reactions
        def check(reaction, user):
            return reaction.message.id == challenge_message.id and str(reaction.emoji) == "✅" and not user.bot

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=86400 * days, check=check)
                self.active_challenge["participants"].append(user.id)
                await self.register_user(user)
            except asyncio.TimeoutError:
                break  # Challenge ended

        self.active_challenge = None  # Reset challenge

    async def register_user(self, user):
        """DM users for registration steps."""
        dm_channel = await user.create_dm()
        await dm_channel.send("🏆 Welcome to the challenge! Please follow the steps to register.")

        # Step 1: Upload Photos
        await dm_channel.send("📸 Step 1: Upload your starting photos (Front, Side, Back).")
        photos = await self.collect_images(user)
        if not photos:
            return

        # Step 2: Name
        await dm_channel.send("🏷️ Step 2: Enter your name/nickname.")
        name = await self.collect_text(user)
        if not name:
            return

        # Step 3: Weight
        await dm_channel.send("⚖️ Step 3: Enter your current weight.")
        weight = await self.collect_text(user)
        if not weight:
            return

        # Step 4: Goal Weight
        await dm_channel.send("🎯 Step 4: Enter your goal weight.")
        goal_weight = await self.collect_text(user)
        if not goal_weight:
            return

        # Step 5: Personal Goal
        await dm_channel.send("✍️ Step 5: Enter your personal goal (e.g., lose 10 lbs, bulk up).")
        personal_goal = await self.collect_text(user)
        if not personal_goal:
            return

        # Save to DB
        async with db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO challenges (user_id, username, initial_photos, current_weight, goal_weight, personal_goal, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'active')
            """, user.id, name, photos, weight, goal_weight, personal_goal)

        await dm_channel.send("✅ Registration complete! Good luck!")

    async def collect_text(self, user):
        """Collects a text response from the user."""
        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=lambda m: m.author == user)
            return message.content
        except asyncio.TimeoutError:
            await user.send("⏳ Timed out! Try again later.")
            return None

    async def collect_images(self, user):
        """Collects images from the user."""
        try:
            message = await self.bot.wait_for("message", timeout=120.0,
                                              check=lambda m: m.author == user and m.attachments)
            return [a.url for a in message.attachments]
        except asyncio.TimeoutError:
            await user.send("⏳ Timed out! Try again later.")
            return None


async def setup(bot):
    await bot.add_cog(Challenge(bot))
