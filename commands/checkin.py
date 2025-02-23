import discord # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib # Used for detecting reused images

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {} # Store image hashes per user to prevent abuse

    def hash_image(self, image_bytes):
        return hashlib.md5(images_bytes).hexdigest() # Generates a hash for the image

    @app_commands.command(name="checkin", description="Log a check-in for gym, weight, or food.")
    @app_commands.describe(category="Specify 'gym', 'weight', or 'food'.")
    async def checkin(self, interaction: discord.Interaction, category: str = None):
        if category is None:
            await interaction.response.send_message(
                "Please specify your check-in type: `gym`, `weight`, or `food`.\n\n"
                "**Example Usage:**\n"
                "• `/checkin gym` (1 point per day, requires a workout photo)\n"
                "• `/checkin weight [your weight]` (1 point per week, requires a scale photo)\n"
                "• `/checkin food` (1 point per day, requires a meal photo)"
            )
            return
        category = category.lower()
        if category

        elif category.lower() == "gym":
            await interaction.response.send_message(
                "✅ Gym check-in recorded! Please upload a **photo of your workout** to earn 1 point. 🏋️‍♂️"
            )
        elif category.lower() == "weight":
            await interaction.response.send_message(
                "⚖️ Weight check-in recorded! Please upload a **photo of your scale** with your current weight to earn 1 point."
            )
        elif category.lower() == "food":
            await interaction.response.send_message(
                "🍽️ Food check-in recorded! Please upload a **photo of your meal** to earn 1 point."
            )
        else:
            await interaction.response.send_message("❌ Invalid category. Please use `gym`, `weight`, or `food`.")

async def setup(bot):
    await bot.add_cog(CheckIn(bot)) # Asynchronous function to add the cog to the bot.