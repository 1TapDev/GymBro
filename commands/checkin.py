import discord  # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib  # Used for detecting reused images
from database import db

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {}  # Store image hashes per user to prevent abuse

    def hash_image(self, image_bytes):
        return hashlib.md5(image_bytes).hexdigest()  # Generates a hash for the image

    @app_commands.command(name="checkin", description="Log a check-in for gym, weight, or food.")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Gym 🏋️‍♂️", value="gym"),
            app_commands.Choice(name="Weight ⚖️", value="weight"),
            app_commands.Choice(name="Food 🍽️", value="food"),
        ]
    )
    async def checkin(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        category = category.value  # Get the selected category value
        user_id = interaction.user.id
        username = interaction.user.name

        await interaction.response.defer()

        # Check cooldown
        cooldown_message = await db.check_cooldown(user_id, category)
        if cooldown_message:
            await interaction.followup.send(cooldown_message)
            return

        workout = None  # Default to None unless user inputs it

        # If category is gym, ask for the workout type
        if category == "gym":
            await interaction.followup.send("🏋️ **Which workout did you do?** Please type it below.")

            def workout_check(m):
                return m.author.id == user_id and isinstance(m.content, str)

            try:
                workout_msg = await self.bot.wait_for("message", timeout=30.0, check=workout_check)
                workout = workout_msg.content  # Store the workout input
            except asyncio.TimeoutError:
                await interaction.followup.send("⏳ You took too long to enter a workout. Please try again.")
                return

        await interaction.followup.send(f"✅ **{category.capitalize()} check-in started!** Please upload a photo.")

        def check(m):
            return m.author.id == interaction.user.id and m.attachments

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
            attachment = message.attachments[0]

            if not attachment.content_type.startswith("image/"):
                await interaction.followup.send("❌ That’s not an image! Please upload a valid photo.")
                return

            image_bytes = await attachment.read()
            image_hash = self.hash_image(image_bytes)

            async with db.pool.acquire() as conn:
                existing_checkin = await conn.fetchrow("""
                    SELECT * FROM checkins WHERE user_id = $1 AND image_hash = $2
                """, user_id, image_hash)

            if existing_checkin:
                await interaction.followup.send("⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            # Log check-in with the workout type
            result = await db.log_checkin(user_id, category, image_hash, workout)

            if result == "success":
                await interaction.followup.send(f"✅ {category.capitalize()} check-in **completed!** You earned 1 point.")
            elif result == "cooldown":
                await interaction.followup.send(f"⏳ You have already checked in for **{category}** today. Try again tomorrow!")
            else:
                await interaction.followup.send("❌ There was an error logging your check-in. Please try again.")

        except asyncio.TimeoutError:
            await interaction.followup.send("⏳ You took too long to upload an image. Please try again.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot))