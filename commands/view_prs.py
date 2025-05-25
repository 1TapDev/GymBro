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
        await interaction.response.defer()
        user_id = interaction.user.id
        pr_data = await db.get_personal_records(user_id)
        pr_videos = await db.get_pr_videos(user_id)

        if not pr_data:
            await interaction.followup.send("❌ No PR records found.")
            return

        if lift:
            lift_name = lift.value
            pr_value = pr_data.get(lift_name, "Not set")

            embed = discord.Embed(
                title=f"🏆 {interaction.user.display_name}'s {lift.name} PR",
                description=f"🏋️ **{lift.name} PR:** {pr_value} lbs",
                color=discord.Color.gold()
            )

            view = BackToProfileView(interaction.user, interaction.client)
            await interaction.edit_original_response(embed=embed, view=view)

            # Send video if available
            video_column = f"{lift_name}_video"
            if video_column in pr_videos and pr_videos[video_column]:
                video_path = pr_videos[video_column]
                if os.path.exists(video_path):
                    file = discord.File(video_path, filename=f"{lift_name}.mp4")
                    await interaction.followup.send(f"✅ {lift.name} PR Attempt:", file=file)
                else:
                    await interaction.followup.send(f"⚠️ No recorded video found for {lift.name} PR.")
            return

        # No lift provided, show summary
        embed = discord.Embed(
            title=f"🏆 {interaction.user.display_name}'s Personal Records",
            description="Your PRs with recorded attempts:",
            color=discord.Color.gold()
        )

        for lift_name in ["deadlift", "bench", "squat"]:
            pr_value = pr_data.get(lift_name, "Not set")
            embed.add_field(name=f"🏋️ {lift_name.capitalize()} PR", value=f"{pr_value} lbs", inline=False)

        view = BackToProfileView(interaction.user, interaction.client)
        await interaction.edit_original_response(embed=embed, view=view)


class BackToProfileView(discord.ui.View):
    def __init__(self, user, bot):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot

    @discord.ui.button(label="🔙 Back to Profile", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            from commands.profile import generate_profile_embeds
            embed1, embed2, view = await generate_profile_embeds(self.user, self.bot, interaction)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed1, view=view)
        except Exception as e:
            print("❌ Back to profile error:", e)
            try:
                await interaction.followup.send("Something went wrong returning to profile.", ephemeral=True)
            except:
                pass



async def setup(bot):
    await bot.add_cog(ViewPRs(bot))
