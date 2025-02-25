import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import db


class PRConfirmationView(View):
    def __init__(self, user_id, lift, new_value, current_value, interaction):
        super().__init__()
        self.user_id = user_id
        self.lift = lift
        self.new_value = new_value
        self.current_value = current_value
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user_id  # Ensure only the command user can interact

    @discord.ui.button(label="✅ Yes", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await db.update_pr(self.user_id, self.lift, self.new_value)

        # Updated confirmation message
        embed = discord.Embed(
            title="✅ PR Updated!",
            description=f"Your **{self.lift.capitalize()} PR** has been set to **{self.new_value} lbs**!",
            color=discord.Color.green()
        )
        embed.set_footer(text="Keep pushing for new PRs! 💪")

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="❌ PR Update Canceled",
            description="Your PR remains unchanged.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class PersonalRecords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pr", description="Set a new personal record (PR).")
    @app_commands.describe(lift="Select a lift to set a new PR.", value="Enter your new PR weight.")
    @app_commands.choices(
        lift=[
            app_commands.Choice(name="Deadlift", value="deadlift"),
            app_commands.Choice(name="Bench Press", value="bench"),
            app_commands.Choice(name="Squat", value="squat")
        ]
    )
    async def pr(self, interaction: discord.Interaction, lift: app_commands.Choice[str], value: int):
        user_id = interaction.user.id
        lift = lift.value

        # Fetch current PR
        pr_data = await db.get_personal_records(user_id)
        current_pr = pr_data[lift] if pr_data and pr_data[lift] else 0

        if value <= 0:
            await interaction.response.send_message("❌ Invalid input. PR value must be greater than 0.")
            return

        # Create confirmation embed
        embed = discord.Embed(
            title="🏋️ Update Personal Record?",
            description=f"Your current **{lift.capitalize()} PR** is **{current_pr} lbs**.\n\nDo you want to update it to **{value} lbs**?",
            color=discord.Color.blue()
        )

        # Send message with confirmation buttons
        await interaction.response.send_message(embed=embed,
                                                view=PRConfirmationView(user_id, lift, value, current_pr, interaction))


async def setup(bot):
    await bot.add_cog(PersonalRecords(bot))
