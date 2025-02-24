import discord
from discord import app_commands
from discord.ext import commands
from database import db
import asyncio  # Needed for handling reactions and timeouts

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="View the leaderboard rankings.")
    async def leaderboard(self, interaction: discord.Interaction):
        leaderboard_data = await db.get_leaderboard()

        if not leaderboard_data:
            print("⚠️ No leaderboard data found!")
            await interaction.response.send_message("🏆 No leaderboard data available yet.")
            return

        # Splitting leaderboard into pages (10 users per page)
        per_page = 10
        pages = [leaderboard_data[i:i + per_page] for i in range(0, len(leaderboard_data), per_page)]
        total_pages = len(pages)

        async def generate_embed(page_index):
            """Generates a leaderboard embed for the given page."""
            embed = discord.Embed(
                title="🏆 Leaderboard",
                description=f"Page {page_index + 1}/{total_pages} - Top users with the most points!",
                color=discord.Color.blue()
            )

            try:
                file = discord.File("assets/logo.png", filename="logo.png")
                embed.set_thumbnail(url="attachment://logo.png")
            except Exception as e:
                file = None  # Ensure the bot doesn't crash if the file is missing

            medals = ["🥇", "🥈", "🥉"]

            leaderboard_text = ""

            for idx, user in enumerate(pages[page_index], start=1 + (page_index * per_page)):
                rank = medals[idx - 1] if idx <= 3 else f"#{idx}"
                leaderboard_text += f"**{rank}** **{user['username']}**: {user['points']} Points\n"

            embed.add_field(name="Ranks", value=leaderboard_text, inline=False)
            embed.set_footer(text="Compete by checking in daily!")

            return embed, file

        # Initial Embed
        page = 0
        embed, file = await generate_embed(page)
        if file:
            message = await interaction.response.send_message(embed=embed, file=file)
        else:
            message = await interaction.response.send_message(embed=embed)

        # If there's only one page, no need for reactions
        if total_pages == 1:
            return

        # Adding reaction buttons for pagination
        await message.add_reaction("⬅️")
        await message.add_reaction("➡️")

        def check(reaction, user):
            return user == interaction.user and reaction.message.id == message.id and reaction.emoji in ["⬅️", "➡️"]

        while True:
            try:
                reaction, user = await interaction.client.wait_for("reaction_add", timeout=60.0, check=check)

                if reaction.emoji == "⬅️" and page > 0:
                    page -= 1
                elif reaction.emoji == "➡️" and page < total_pages - 1:
                    page += 1
                else:
                    continue  # Ignore invalid reactions

                # Generate new page
                embed, file = await generate_embed(page)
                await message.edit(embed=embed)
                await message.remove_reaction(reaction, user)  # Remove user's reaction for smooth experience

            except asyncio.TimeoutError:
                break  # Stop listening after timeout

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))