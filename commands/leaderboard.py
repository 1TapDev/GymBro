import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="View the leaderboard rankings.")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.send_message("📊 Leaderboard rankings will be displayed here!")

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
