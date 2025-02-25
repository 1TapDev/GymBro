import discord  # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib  # Used for detecting reused images
import os  # Used for handling file paths
from database import db

# Folder to store images
IMAGE_FOLDER = "checkin_images"

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {}  # Store image hashes per user to prevent abuse

    def hash_image(self, image_bytes):
        return hashlib.md5(image_bytes).hexdigest()  # Generates a hash for the image

    def save_image_locally(self, user_id, image_hash, image_bytes):
        """Save image in a user-specific folder with a hashed filename and return the file path."""
        user_folder = os.path.join(IMAGE_FOLDER, str(user_id))  # Folder for each user
        os.makedirs(user_folder, exist_ok=True)  # Ensure the folder exists

        image_path = os.path.join(user_folder, f"{image_hash}.jpg")  # Save as JPG
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        return image_path  # Return saved file path

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

        # Require a message input before image upload
        response_text = None
        if category == "gym":
            prompt_text = "🏋️ **Which workout did you do?** Please type it below."
        elif category == "weight":
            prompt_text = "⚖️ **Please enter your weight in pounds (e.g., 175.5):**"
        elif category == "food":
            prompt_text = "🍽️ **What meal did you have?** Please describe it."

        await interaction.followup.send(prompt_text)

        def text_check(m):
            return (
                m.author.id == user_id
                and isinstance(m.content, str)
                and not m.attachments  # Ensure no images are included
            )

        while True:
            try:
                message = await self.bot.wait_for("message", timeout=30.0)

                # If the message contains an attachment (image), send an error message and retry
                if message.attachments:
                    await interaction.followup.send("❌ **Please type your response instead of uploading an image.** Try again.")
                    continue

                if text_check(message):  # Valid text input
                    response_text = message.content
                    break

            except asyncio.TimeoutError:
                await interaction.followup.send("⏳ You took too long to enter a response. Please try again.")
                return

        # If weight check-in, ensure the input is a valid number
        if category == "weight":
            try:
                weight = float(response_text)
            except ValueError:
                await interaction.followup.send("❌ Invalid weight input. Please enter a numeric value (e.g., 175.5).")
                return
        else:
            weight = None

        # Step 2: Require Image Upload AFTER Text Response
        await interaction.followup.send(f"✅ **{category.capitalize()} check-in started!** Now, please upload a photo.")

        def image_check(m):
            return m.author.id == user_id and any(a.content_type.startswith("image/") for a in m.attachments)

        try:
            image_message = await self.bot.wait_for("message", timeout=60.0, check=image_check)
            attachment = image_message.attachments[0]

            image_bytes = await attachment.read()
            image_hash = self.hash_image(image_bytes)

            # Save image locally and get its path
            image_path = self.save_image_locally(user_id, image_hash, image_bytes)

            async with db.pool.acquire() as conn:
                existing_checkin = await conn.fetchrow("""
                    SELECT * FROM checkins WHERE user_id = $1 AND image_hash = $2
                """, user_id, image_hash)

            if existing_checkin:
                await interaction.followup.send("⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            # Log check-in with the image path
            result = await db.log_checkin(user_id, category, image_hash, image_path, response_text, weight)

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
