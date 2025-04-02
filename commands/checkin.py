import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib
import os
from database import db
from PIL import Image

IMAGE_FOLDER = "checkin_images"
MAX_IMAGE_SIZE = (600, 600)

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {}

    def hash_image(self, image_bytes):
        return hashlib.md5(image_bytes).hexdigest()

    def save_image_locally(self, user_id, image_hash, image_bytes):
        user_folder = os.path.join(IMAGE_FOLDER, str(user_id))
        os.makedirs(user_folder, exist_ok=True)

        original_path = os.path.join(user_folder, f"{image_hash}.webp")
        with open(original_path, "wb") as f:
            f.write(image_bytes)

        try:
            img = Image.open(original_path)
            img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)
            img.save(original_path, "WEBP", quality=85, optimize=True)
        except Exception as e:
            print(f"Error compressing image {original_path}: {e}")

        return original_path

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
                existing_checkin = await conn.fetchrow(
                    "SELECT * FROM checkins WHERE user_id = $1 AND image_hash = $2",
                    user_id, image_hash
                )

            if existing_checkin:
                await interaction.followup.send("⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            result = await db.log_checkin(user_id, username, category, image_hash, image_path, response_text, weight)

            if result in ["success_with_point", "success_no_point"]:
                await image_message.delete()
                await upload_prompt.delete()

                if not os.path.exists(image_path):
                    print(f"❌ Image file not found: {image_path}")
                    await interaction.followup.send("⚠️ Image not found. Please try again.")
                    return

                file = discord.File(image_path, filename="checkin.webp")
                embed = discord.Embed(
                    title=f"✅ {category.capitalize()} Check-In Completed!",
                    description=f"**{username}** checked in for **{category}**.\n**{response_text}**",
                    color=discord.Color.green()
                )
                embed.set_image(url="attachment://checkin.webp")

                footer = "You earned 1 point!" if result == "success_with_point" else "Check-in recorded. No point earned today."
                embed.set_footer(text=footer)

                await interaction.followup.send(embed=embed, file=file)

            else:
                await interaction.followup.send("❌ There was an error logging your check-in. Please try again.")

        except asyncio.TimeoutError:
            await upload_prompt.delete()
            await interaction.followup.send("⏳ You took too long to upload an image. Please try again.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot))
