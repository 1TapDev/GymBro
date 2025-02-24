import discord
from discord import app_commands
from discord.ext import commands
from database import db

class PersonalRecords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pr", description="View or set your personal records (PRs).")
    @app_commands.describe(action="Choose 'set' to update a PR or 'view' to see all PRs.", lift="Select a lift to set a new PR.", value="Enter your new PR weight (only for 'set').")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Set PR", value="set"),
            app_commands.Choice(name="View PRs", value="view")
        ],
        lift=[
            app_commands.Choice(name="Deadlift", value="deadlift"),
            app_commands.Choice(name="Bench Press", value="bench"),
            app_commands.Choice(name="Squat", value="squat")
        ]
    )
    async def pr(self, interaction: discord.Interaction, action: app_commands.Choice[str], lift: app_commands.Choice[str] = None, value: int = None):
        user_id = interaction.user.id
        action = action.value
        lift = lift.value if lift else None

        if action == "view":
            # Fetch PRs from the database
            pr_data = await db.get_personal_records(user_id)

            if not pr_data:
                await interaction.response.send_message("📊 No personal records found. Use `/pr set` to set your first PR!")
                return

            # Extract PR values, default to 0 if None
            deadlift = pr_data["deadlift"] or 0
            bench = pr_data["bench"] or 0
            squat = pr_data["squat"] or 0

            # Create embed
            embed = discord.Embed(
                title="🏆 Personal Records",
                color=discord.Color.gold()
            )
            embed.add_field(name="🏋️ Deadlift", value=f"**{deadlift} lbs**", inline=False)
            embed.add_field(name="🏋️‍♂️ Bench Press", value=f"**{bench} lbs**", inline=False)
            embed.add_field(name="🏋️‍♀️ Squat", value=f"**{squat} lbs**", inline=False)
            embed.set_footer(text="Keep pushing for new PRs!")

            await interaction.response.send_message(embed=embed)
            return

        elif action == "set":
            if not lift or value is None or value <= 0:
                await interaction.response.send_message("❌ Invalid input. Use `/pr set <lift> <number>` to set a new PR.")
                return

            # Update PR in the database
            await db.update_pr(user_id, lift, value)

            await interaction.response.send_message(f"✅ Your new **{lift.capitalize()} PR** is set to **{value} lbs**! Keep pushing!")

async def setup(bot):
    await bot.add_cog(PersonalRecords(bot))
