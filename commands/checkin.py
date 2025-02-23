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
        print(f"📥 Received /checkin command from {username} (ID: {user_id}) - Category: {category}")
        # Add user to database before logging check-in
        await db.add_user(user_id, username)
        # Log the check-in
        await db.log_checkin(user_id, category)

        await interaction.response.send_message(
            f"✅ **{category.capitalize()} check-in started!** Please upload a photo."
        )

        def check(m):
            return m.author.id == interaction.user.id and m.attachments  # Check if user sends an image

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)  # Wait for user to upload an image
            attachment = message.attachments[0]

            if not attachment.content_type.startswith("image/"):  # Ensure the file is an image
                await interaction.followup.send("❌ That’s not an image! Please upload a valid photo.")
                return

            image_bytes = await attachment.read()
            image_hash = self.hash_image(image_bytes)

            # Check if the user has uploaded this image before
            if interaction.user.id in self.previous_images and image_hash in self.previous_images[interaction.user.id]:
                await interaction.followup.send(
                    "⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            # Store the new image hash for this user
            if interaction.user.id not in self.previous_images:
                self.previous_images[interaction.user.id] = set()
            self.previous_images[interaction.user.id].add(image_hash)

            await interaction.followup.send(f"✅ {category.capitalize()} check-in **completed!** You earned 1 point.")

        except asyncio.TimeoutError:
            await interaction.followup.send("⏳ You took too long to upload an image. Please try again.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot))