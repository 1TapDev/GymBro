import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Progress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="progress", description="Displays your progress summary.")
    async def progress(self, interaction: discord.Interaction):
        progress_data = await db.get_progress(interaction.user.id)

        if not progress_data:
            await interaction.response.send_message("❌ No progress data found. Start tracking with !checkin.")
            return

        gym_checkins, food_logs, weight_change = progress_data

        await interaction.response.send_message(
            f"📊 **Progress Summary for {interaction.user.name}**\n"
            f"🏋️ Gym Check-ins: **{gym_checkins}**\n"
            f"🍽️ Food Logs: **{food_logs}**\n"
            f"⚖️ Total Weight Change: **{weight_change} lbs**"
        )

    @app_commands.command(name="pr", description="View or set personal records.")
    async def pr(self, interaction: discord.Interaction):
        pr_data = await db.get_personal_records(interaction.user.id)

        if not pr_data:
            await interaction.response.send_message("❌ No PRs recorded yet. Set a PR using !pr set [lift] [weight].")
            return

        deadlift, bench, squat = pr_data

        await interaction.response.send_message(
            f"🏆 **Personal Records for {interaction.user.name}**\n"
            f"🏋️ Deadlift: **{deadlift} lbs**\n"
            f"💪 Bench Press: **{bench} lbs**\n"
            f"🦵 Squat: **{squat} lbs**"
        )

async def setup(bot):
    await bot.add_cog(Progress(bot))