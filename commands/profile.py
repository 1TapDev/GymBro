import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import db
import os


class ProfileView(View):
    def __init__(self, user, embed1, embed2, bot):
        super().__init__(timeout=120)
        self.user = user
        self.embed1 = embed1
        self.embed2 = embed2
        self.bot = bot
        self.current_page = 1
        self.update_buttons()

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, Button) and hasattr(child, 'custom_id'):
                if child.custom_id == "page_prev":
                    child.disabled = self.current_page == 1
                elif child.custom_id == "page_next":
                    child.disabled = self.current_page == 2

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=0, custom_id="page_prev")
    async def previous(self, interaction: discord.Interaction, button: Button):
        self.current_page = 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed1, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=0, custom_id="page_next")
    async def next(self, interaction: discord.Interaction, button: Button):
        self.current_page = 2
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed2, view=self)

    @discord.ui.button(label="🏋️ Gym Check-ins", style=discord.ButtonStyle.success, row=1, custom_id="checkin_gym")
    async def gym_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "gym")

    @discord.ui.button(label="⚖️ Weight Check-ins", style=discord.ButtonStyle.success, row=1, custom_id="checkin_weight")
    async def weight_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "weight")

    @discord.ui.button(label="🍽️ Food Check-ins", style=discord.ButtonStyle.success, row=1, custom_id="checkin_food")
    async def food_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "food")

    @discord.ui.button(label="🏋️ Deadlift PR", style=discord.ButtonStyle.danger, row=2, custom_id="pr_deadlift")
    async def deadlift_pr(self, interaction: discord.Interaction, button: Button):
        await self._handle_pr(interaction, "deadlift")

    @discord.ui.button(label="🏋️ Bench Press PR", style=discord.ButtonStyle.danger, row=2, custom_id="pr_bench")
    async def bench_pr(self, interaction: discord.Interaction, button: Button):
        await self._handle_pr(interaction, "bench")

    @discord.ui.button(label="🏋️ Squat PR", style=discord.ButtonStyle.danger, row=2, custom_id="pr_squat")
    async def squat_pr(self, interaction: discord.Interaction, button: Button):
        await self._handle_pr(interaction, "squat")

    async def _handle_checkin(self, interaction, category):
        checkin_cog = self.bot.get_cog("ViewCheckIn")
        if not checkin_cog:
            await interaction.response.send_message("❌ Check-in viewer not loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        checkins = await db.get_user_checkins(self.user.id, category)
        if not checkins:
            await interaction.followup.send(f"🚫 {self.user.mention} has no {category} check-ins yet!")
            return

        await checkin_cog.send_checkin_page(interaction, checkins, page=0, category=category, target_user=self.user)

    async def _handle_pr(self, interaction, lift):
        try:
            await interaction.response.defer()
            pr_data = await db.get_personal_records(self.user.id)
            pr_videos = await db.get_pr_videos(self.user.id)

            pr_value = pr_data.get(lift, "Not set")

            embed = discord.Embed(
                title=f"🏆 {self.user.display_name}'s {lift.capitalize()} PR",
                description=f"🏋️ **{lift.capitalize()} PR:** {pr_value} lbs",
                color=discord.Color.orange()
            )

            await interaction.edit_original_response(embed=embed, view=BackToProfileView(self.user, self.bot))

            video_column = f"{lift}_video"
            if video_column in pr_videos and pr_videos[video_column]:
                video_path = pr_videos[video_column]
                if os.path.exists(video_path):
                    file = discord.File(video_path, filename=f"{lift}.mp4")
                    await interaction.followup.send(f"✅ {lift.capitalize()} PR Attempt:", file=file)
                else:
                    await interaction.followup.send(f"⚠️ No recorded video found for {lift.capitalize()} PR.")
        except Exception as e:
            print(f"❌ PR button error: {e}")
            try:
                await interaction.followup.send("Something went wrong loading this PR.", ephemeral=True)
            except:
                pass


class BackToProfileView(discord.ui.View):
    def __init__(self, user, bot):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot

    @discord.ui.button(label="🔙 Back to Profile", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: Button):
        try:
            from commands.profile import generate_profile_embeds
            embed1, embed2, view = await generate_profile_embeds(self.user, self.bot, interaction)
            await interaction.edit_original_response(embed=embed1, view=view)
        except Exception as e:
            print("❌ Back to profile error:", e)
            try:
                await interaction.response.send_message("Something went wrong returning to profile.", ephemeral=True)
            except:
                pass


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="View your fitness profile (points, check-ins, PRs)")
    @app_commands.describe(user="Whose profile do you want to view?")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()
        try:
            target_user = user or interaction.user
            embed1, embed2, view = await generate_profile_embeds(target_user, self.bot, interaction)
            await interaction.followup.send(embed=embed1, view=view)
        except Exception as e:
            print("❌ Profile command error:", e)
            await interaction.followup.send("Something went wrong loading your profile.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Profile(bot))


# Profile Embed Generator
async def generate_profile_embeds(user, bot, interaction):
    user_id = user.id
    points = await db.get_user_points(user_id)
    progress = await db.get_progress(user_id)
    gym = progress.get("total_gym_checkins", 0)
    food = progress.get("total_food_logs", 0)
    first_weight, recent_weight, weight_change = await db.get_weight_change(user_id)
    trend = "🔼" if weight_change > 0 else "🔽" if weight_change < 0 else "⚖️"
    weight_display = f"{weight_change} lbs {trend} (**{recent_weight} lbs**)" if recent_weight else "⚖️ No weight data"

    embed1 = discord.Embed(
        title=f"📋 {user.display_name}'s Profile – Page 1",
        description="Here’s your fitness journey so far 💪",
        color=discord.Color.teal()
    )
    embed1.set_thumbnail(url=user.display_avatar.url)
    embed1.add_field(name="🏆 Total Points", value=f"**{points}**", inline=False)
    embed1.add_field(name="**─── Check-in Summary ───**", value="\u200b", inline=False)
    embed1.add_field(name="💪 Gym Check-ins", value=f"**{gym}**", inline=False)
    embed1.add_field(name="🍽️ Food Logs", value=f"**{food}**", inline=False)
    embed1.add_field(name="⚖️ Weight Change", value=weight_display, inline=False)
    embed1.set_footer(text="Page 1/2 – Click 'Next' for PRs")

    rankings = await db.get_pr_rankings()
    pr_data = await db.get_personal_records(user_id)

    def get_medal(lift_type):
        sorted_prs = rankings.get(lift_type, [])
        for idx, (u_id, _) in enumerate(sorted_prs[:8]):
            if u_id == user_id:
                return ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"][idx]
        return "🏆"

    deadlift = pr_data["deadlift"] or 0 if pr_data else 0
    bench = pr_data["bench"] or 0 if pr_data else 0
    squat = pr_data["squat"] or 0 if pr_data else 0

    embed2 = discord.Embed(
        title=f"🏋️ {user.display_name}'s Personal Records – Page 2",
        description="Your top lifts with leaderboard medals",
        color=discord.Color.gold()
    )
    embed2.set_thumbnail(url=user.display_avatar.url)
    embed2.add_field(name="🏋️‍♂️ Deadlift", value=f"**{deadlift} lbs** {get_medal('deadlift')}", inline=False)
    embed2.add_field(name="🏋️‍♂️ Bench Press", value=f"**{bench} lbs** {get_medal('bench')}", inline=False)
    embed2.add_field(name="🏋️‍♀️ Squat", value=f"**{squat} lbs** {get_medal('squat')}", inline=False)
    embed2.set_footer(text="Page 2/2 – Click 'Previous' to go back")

    view = ProfileView(user, embed1, embed2, bot)
    return embed1, embed2, view
