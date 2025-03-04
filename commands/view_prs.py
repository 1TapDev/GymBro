import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os


class ViewPRs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="view_prs", description="View your PRs with recorded attempts.")
    @app_commands.describe(lift="Specify a lift to view its PR and video (optional).")
    @app_commands.choices(
        lift=[
            app_commands.Choice(name="Deadlift", value="deadlift"),
            app_commands.Choice(name="Bench Press", value="bench"),
            app_commands.Choice(name="Squat", value="squat")
        ]
    )
    async def view_prs(self, interaction: discord.Interaction, lift: app_commands.Choice[str] = None):
        user_id = interaction.user.id
        pr_data = await db.get_personal_records(user_id)
        pr_videos = await db.get_pr_videos(user_id)  # Fetch PR videos

        if not pr_data:
            await interaction.response.send_message("❌ No PR records found.")
            return

        if lift:  # If a specific lift is requested, show only that PR and video
            lift_name = lift.value
            pr_value = pr_data.get(lift_name, "Not set")

            embed = discord.Embed(
                title=f"🏆 {interaction.user.display_name}'s {lift.name} PR",
                description=f"🏋️ **{lift.name} PR:** {pr_value} lbs",
                color=discord.Color.gold()
            )

            await interaction.response.send_message(embed=embed)

            # Check if there's a video for this PR
            video_column = f"{lift_name}_video"
            if video_column in pr_videos and pr_videos[video_column]:
                video_path = pr_videos[video_column]
                if os.path.exists(video_path):  # Ensure file exists before sending
                    file = discord.File(video_path, filename=f"{lift_name}.mp4")
                    await interaction.followup.send(f"✅ {lift.name} PR Attempt:", file=file)
                else:
                    await interaction.followup.send(f"⚠️ No recorded video found for {lift.name} PR.")
            return

        # Default: Show all PRs (when no lift is specified)
        embed = discord.Embed(
            title=f"🏆 {interaction.user.display_name}'s Personal Records",
            description="Your PRs with recorded attempts:",
            color=discord.Color.gold()
        )

        for lift_name in ["deadlift", "bench", "squat"]:
            pr_value = pr_data.get(lift_name, "Not set")
            embed.add_field(name=f"🏋️ {lift_name.capitalize()} PR", value=f"{pr_value} lbs", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ViewPRs(bot))
