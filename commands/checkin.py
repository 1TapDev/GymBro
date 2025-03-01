import discord  # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib  # Used for detecting reused images
import os  # Used for handling file paths
from database import db
from PIL import Image  # Pillow for image resizing

# Folder to store images
IMAGE_FOLDER = "checkin_images"
MAX_IMAGE_SIZE = (300, 300)  # Resize images to 300x300 pixels

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {}

    def hash_image(self, image_bytes):
        """Generate a hash for the image to prevent duplicates."""
        return hashlib.md5(image_bytes).hexdigest()

    def resize_image(self, image_path):
        """Resize image before saving to limit its size and remove the original image."""
        try:
            img = Image.open(image_path)
            img.thumbnail(MAX_IMAGE_SIZE)  # Resize while maintaining aspect ratio

            resized_path = image_path.replace(".jpg", "_small.jpg")
            img.save(resized_path, "JPEG", quality=85)  # Save resized image

            # **Delete the original file**
            os.remove(image_path)

            return resized_path  # Return new resized file path
        except Exception as e:
            print(f"Error resizing image {image_path}: {e}")
            return image_path  # Fallback to original image if resizing fails

    def save_image_locally(self, user_id, image_hash, image_bytes):
        """Save and resize image locally, then return its file path."""
        user_folder = os.path.join(IMAGE_FOLDER, str(user_id))
        os.makedirs(user_folder, exist_ok=True)

        original_path = os.path.join(user_folder, f"{image_hash}.jpg")
        with open(original_path, "wb") as f:
            f.write(image_bytes)

        # Resize the image before saving to the database
        resized_path = self.resize_image(original_path)
        return resized_path  # Return resized image path

    @app_commands.command(name="checkin", description="Log a check-in for gym, weight, or food.")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Gym 🏋️‍♂️", value="gym"),
            app_commands.Choice(name="Weight ⚖️", value="weight"),
            app_commands.Choice(name="Food 🍽️", value="food"),
        ]
    )
    async def checkin(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        category = category.value
        user_id = interaction.user.id
        username = interaction.user.name

        await interaction.response.defer()

        cooldown_message = await db.check_cooldown(user_id, category)
        if cooldown_message:
            await interaction.followup.send(cooldown_message)
            return

        response_text = None
        prompt_text = {
            "gym": "🏋️ **Which workout did you do?** Please type it below.",
            "weight": "⚖️ **Please enter your weight in pounds (e.g., 175.5):**",
            "food": "🍽️ **What meal did you have?** Please describe it."
        }[category]

        prompt_message = await interaction.followup.send(prompt_text)

        def text_check(m):
            return m.author.id == user_id and not m.attachments

        try:
            message = await self.bot.wait_for("message", timeout=30.0, check=text_check)
            response_text = message.content
            await message.delete()
            await prompt_message.delete()
        except asyncio.TimeoutError:
            await prompt_message.delete()
            await interaction.followup.send("⏳ You took too long to enter a response. Please try again.")
            return

        weight = None
        if category == "weight":
            try:
                weight = float(response_text)
            except ValueError:
                await interaction.followup.send("❌ Invalid weight input. Please enter a numeric value (e.g., 175.5).")
                return

        upload_prompt = await interaction.followup.send(f"✅ **{category.capitalize()} check-in started!** Now, please upload a photo.")

        def image_check(m):
            return m.author.id == user_id and any(a.content_type.startswith("image/") for a in m.attachments)

        try:
            image_message = await self.bot.wait_for("message", timeout=60.0, check=image_check)
            attachment = image_message.attachments[0]

            image_bytes = await attachment.read()
            image_hash = self.hash_image(image_bytes)
            image_path = self.save_image_locally(user_id, image_hash, image_bytes)

            async with db.pool.acquire() as conn:
                existing_checkin = await conn.fetchrow("SELECT * FROM checkins WHERE user_id = $1 AND image_hash = $2", user_id, image_hash)

            if existing_checkin:
                await interaction.followup.send("⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            result = await db.log_checkin(user_id, username, category, image_hash, image_path, response_text, weight)

            if result == "success":
                await image_message.delete()
                await upload_prompt.delete()

                if not os.path.exists(image_path):
                    print(f"❌ Image file not found: {image_path}")
                    await interaction.followup.send("⚠️ Image not found. Please try again.")
                    return

                file = discord.File(image_path, filename="checkin.jpg")
                embed = discord.Embed(
                    title="✅ Gym Check-In Completed!",
                    description=f"**{username}** checked in for **{category}**.\n**{response_text}**",
                    color=discord.Color.green()
                )
                embed.set_image(url="attachment://checkin.jpg")
                embed.set_footer(text="You earned 1 point!")

                await interaction.followup.send(embed=embed, file=file)

            elif result == "cooldown":
                await interaction.followup.send(f"⏳ You have already checked in for **{category}** today. Try again tomorrow!")
            else:
                await interaction.followup.send("❌ There was an error logging your check-in. Please try again.")

        except asyncio.TimeoutError:
            await upload_prompt.delete()
            await interaction.followup.send("⏳ You took too long to upload an image. Please try again.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot))
