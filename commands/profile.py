import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
from database import db


class CheckInDropdown(discord.ui.Select):
    def __init__(self, user, bot):
        self.user = user
        self.bot = bot
        options = [
            discord.SelectOption(label="Gym 🏋️", value="gym", description="View gym check-ins"),
            discord.SelectOption(label="Weight ⚖️", value="weight", description="View weight check-ins"),
            discord.SelectOption(label="Food 🍽️", value="food", description="View food check-ins")
        ]
        super().__init__(placeholder="Choose a check-in category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        checkin_cog = self.bot.get_cog("ViewCheckIn")
        if not checkin_cog:
            await interaction.response.send_message("❌ Check-in viewer is not loaded.", ephemeral=True)
            return

        category = self.values[0]
        await interaction.response.defer()
        checkins = await db.get_user_checkins(self.user.id, category)
        if not checkins:
            await interaction.followup.send(f"🚫 {self.user.mention} has no {category} check-ins yet!")
            return

        await checkin_cog.send_checkin_page(interaction, checkins, page=0, category=category, target_user=self.user)


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
            if isinstance(child, Button):
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

    @discord.ui.button(label="🏋️ Gym Check-ins", style=discord.ButtonStyle.success, row=1)
    async def gym_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "gym")

    @discord.ui.button(label="⚖️ Weight Check-ins", style=discord.ButtonStyle.success, row=2)
    async def weight_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "weight")

    @discord.ui.button(label="🍽️ Food Check-ins", style=discord.ButtonStyle.success, row=3)
    async def food_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_checkin(interaction, "food")

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


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="View your fitness profile (points, check-ins, PRs)")
    @app_commands.describe(user="Whose profile do you want to view?")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user
        user_id = target_user.id
        mention = target_user.mention

        # PAGE 1 DATA
        points = await db.get_user_points(user_id)
        progress = await db.get_progress(user_id)
        if not progress:
            await interaction.response.send_message(f"{mention} has no progress data yet!")
            return

        gym = progress.get("total_gym_checkins", 0)
        food = progress.get("total_food_logs", 0)

        first_weight, recent_weight, weight_change = await db.get_weight_change(user_id)
        if first_weight is not None and recent_weight is not None:
            trend = "🔼" if weight_change > 0 else "🔽" if weight_change < 0 else "⚖️"
            weight_display = f"{weight_change} lbs {trend} (**{recent_weight} lbs**)"
        else:
            weight_display = "⚖️ No weight data"

        embed1 = discord.Embed(
            title=f"📋 {target_user.display_name}'s Profile – Page 1",
            description="Here’s your fitness journey so far 💪",
            color=discord.Color.teal()
        )
        embed1.set_thumbnail(url=target_user.display_avatar.url)
        embed1.add_field(name="🏆 Total Points", value=f"**{points}**", inline=False)
        embed1.add_field(name="**─── Check-in Summary ───**", value="\u200b", inline=False)
        embed1.add_field(name="💪 Gym Check-ins", value=f"**{gym}**", inline=False)
        embed1.add_field(name="🍽️ Food Logs", value=f"**{food}**", inline=False)
        embed1.add_field(name="⚖️ Weight Change", value=weight_display, inline=False)
        embed1.set_footer(text="Page 1/2 – Click 'Next' for PRs")

        # PAGE 2 DATA – PRs
        rankings = await db.get_pr_rankings()

        def get_medal(lift_type):
            sorted_prs = rankings.get(lift_type, [])
            for idx, (u_id, _) in enumerate(sorted_prs[:8]):
                if u_id == user_id:
                    return ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"][idx]
            return "🏆"

        pr_data = await db.get_personal_records(user_id)
        deadlift = pr_data["deadlift"] or 0 if pr_data else 0
        bench = pr_data["bench"] or 0 if pr_data else 0
        squat = pr_data["squat"] or 0 if pr_data else 0

        deadlift_medal = get_medal("deadlift")
        bench_medal = get_medal("bench")
        squat_medal = get_medal("squat")

        embed2 = discord.Embed(
            title=f"🏋️ {target_user.display_name}'s Personal Records – Page 2",
            description="Your top lifts with leaderboard medals",
            color=discord.Color.gold()
        )
        embed2.set_thumbnail(url=target_user.display_avatar.url)
        embed2.add_field(name="🏋️‍♂️ Deadlift", value=f"**{deadlift} lbs** {deadlift_medal}", inline=False)
        embed2.add_field(name="🏋️‍♂️ Bench Press", value=f"**{bench} lbs** {bench_medal}", inline=False)
        embed2.add_field(name="🏋️‍♀️ Squat", value=f"**{squat} lbs** {squat_medal}", inline=False)
        embed2.set_footer(text="Page 2/2 – Click 'Previous' to go back")

        view = ProfileView(target_user, embed1, embed2, self.bot)
        await interaction.response.send_message(embed=embed1, view=view)


async def setup(bot):
    await bot.add_cog(Profile(bot))
