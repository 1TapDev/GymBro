import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Progress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="progress", description="View your fitness progress.")
    async def progress(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        # Fetch progress from the database
        progress_data = await db.get_progress(user_id)

        if not progress_data:
            await interaction.response.send_message("📊 No progress data found. Start checking in to track progress!")
            return

        # Extract progress values, default to 0 if None
        total_gym_checkins = progress_data["total_gym_checkins"] or 0
        total_food_logs = progress_data["total_food_logs"] or 0
        total_weight_change = progress_data["total_weight_change"] or 0

        # Create embed message
        embed = discord.Embed(
            title="📊 Your Progress",
            color=discord.Color.green()  # Green for positive progress
        )
        embed.add_field(name="💪 Gym Check-ins", value=f"{total_gym_checkins}", inline=False)
        embed.add_field(name="🍽️ Food Logs", value=f"{total_food_logs}", inline=False)
        embed.add_field(name="⚖️ Weight Change", value=f"{total_weight_change} lbs 🔽" if total_weight_change < 0 else f"{total_weight_change} lbs 🔼", inline=False)

        embed.set_footer(text="Keep checking in to track your progress!")

        # Send response
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Progress(bot))
