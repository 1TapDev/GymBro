import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="points", description="Check how many points you or another user have.")
    async def points(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user  # Defaults to command sender if no user is provided
        user_id = target_user.id
        user_mention = target_user.mention  # Mention the target user
        print(f"📊 Fetching points for user {user_id}...")

        async with db.pool.acquire() as conn:
            points = await conn.fetchval("""
                SELECT points FROM users WHERE user_id = $1
            """, user_id)

        if points is None:
            embed = discord.Embed(
                title="🏆 Points Check",
                description=f"{user_mention} doesn't have any points yet! ❌",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="🏆 Points Check",
                description=f"{user_mention} currently has **{points} points!** 🎉",
                color=discord.Color.gold()
            )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Points(bot))
