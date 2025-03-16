import discord
from discord import app_commands
from discord.ext import commands
from database import db

class PrizeSuggestion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="suggest_prize", description="Suggest a prize for 1st place in GNC.")
    async def suggest_prize(self, interaction: discord.Interaction):
        """Allows users to suggest a prize from GNC."""
        await interaction.response.send_message("🏆 What prize would you like from GNC?", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
            prize_suggestion = message.content

            # Save the suggestion to the database
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO prize_suggestions (user_id, username, prize)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET prize = EXCLUDED.prize;
                """, interaction.user.id, interaction.user.name, prize_suggestion)

            # Delete the user's message and bot's prompt
            await message.delete()
            await prompt_message.delete()

            # Confirm deletion
            confirmation = await interaction.followup.send("✅ Your prize suggestion has been recorded!", ephemeral=True)
            await asyncio.sleep(5)  # Keep the confirmation for 5 seconds
            await confirmation.delete()

        except asyncio.TimeoutError:
            await prompt_message.delete()
            await interaction.followup.send("⏳ You took too long to respond. Try again!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PrizeSuggestion(bot))