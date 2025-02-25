import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="points", description="Check how many points you have.")
    async def points(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_mention = interaction.user.mention  # Mention the user
        print(f"📊 Fetching points for user {user_id}...")

        async with db.pool.acquire() as conn:
            points = await conn.fetchval("""
                SELECT points FROM users WHERE user_id = $1
            """, user_id)

        if points is None:
            embed = discord.Embed(
                title="🏆 Points Check",
                description=f"{user_mention}, you don't have any points yet! ❌",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="🏆 Points Check",
                description=f"{user_mention}, you currently have **{points} points!** 🎉",
                color=discord.Color.gold()
            )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Points(bot))
