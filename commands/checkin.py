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

        workout = None  # Default to None unless user inputs it
        weight = None  # Default to None for weight logging
        meal = None  # Default to None for food logging

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

        # If category is weight, ask for weight input
        if category == "weight":
            await interaction.followup.send("⚖️ **Please enter your weight in pounds (e.g., 175.5):**")

            def weight_check(m):
                return m.author.id == user_id and m.content.replace(".", "", 1).isdigit()

            try:
                weight_msg = await self.bot.wait_for("message", timeout=30.0, check=weight_check)
                weight = float(weight_msg.content)  # Convert weight to float
            except asyncio.TimeoutError:
                await interaction.followup.send("⏳ You took too long to enter your weight. Please try again.")
                return
            except ValueError:
                await interaction.followup.send("❌ Invalid weight input. Please enter a numeric value (e.g., 175.5).")
                return

        # If category is food, ask for meal description
        if category == "food":
            await interaction.followup.send("🍽️ **What meal did you have?** Please describe it.")

            def meal_check(m):
                return m.author.id == user_id and isinstance(m.content, str)

            try:
                meal_msg = await self.bot.wait_for("message", timeout=30.0, check=meal_check)
                meal = meal_msg.content  # Store the meal input
            except asyncio.TimeoutError:
                await interaction.followup.send("⏳ You took too long to enter your meal. Please try again.")
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
            result = await db.log_checkin(user_id, category, image_hash, image_path, workout, weight, meal)

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
