import discord  # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib  # Used for detecting reused images

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

        if category == "gym":
            await interaction.response.send_message(
                "✅ Gym check-in recorded! Please upload a **photo of your workout** to earn 1 point. 🏋️‍♂️"
            )
        elif category == "weight":
            await interaction.response.send_message(
                "⚖️ Weight check-in recorded! Please upload a **photo of your scale** with your current weight to earn 1 point."
            )
        elif category == "food":
            await interaction.response.send_message(
                "🍽️ Food check-in recorded! Please upload a **photo of your meal** to earn 1 point."
            )
        else:
            await interaction.response.send_message("❌ Invalid category. Please use `gym`, `weight`, or `food`.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot))  # Asynchronous function to add the cog to the bot.
