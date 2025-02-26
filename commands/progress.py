import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from database import db

class ProgressView(View):
    def __init__(self, target_user, progress_embed, pr_embed):
        super().__init__()
        self.user_id = user_id
        self.target_user = target_user  # Stores the mentioned user's ID
        self.pr_embed = pr_embed
        self.current_page = 1
        self.update_buttons()
        print(f"📜 ProgressView initialized for user {user_id}")

    async def interaction_check(self, interaction: discord.Interaction):
        return True  # 🔥 Allow anyone to interact with the buttons!

    def update_buttons(self):
        """Enable or disable buttons based on the current page."""
        for child in self.children:
            if isinstance(child, Button):
                if child.label == "Previous":
                    child.disabled = self.current_page == 1  # Disable on Page 1
                elif child.label == "Next":
                    child.disabled = self.current_page == 2  # Disable on Page 2

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        self.current_page = 1
        self.update_buttons()
        print(f"🔄 {interaction.user.id} switched to Page 1")
        await interaction.response.edit_message(embed=self.progress_embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page = 2
        self.update_buttons()
        print(f"🔄 {interaction.user.id} switched to Page 2")
        await interaction.response.edit_message(embed=self.pr_embed, view=self)

class Progress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="progress", description="View your fitness progress or someone else's.")
    async def progress(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user  # Defaults to command sender if no user is provided
        user_id = target_user.id
        user_mention = target_user.mention  # Mention the target user

        try:
            print("🔄 Fetching progress data from database...")
            progress_data = await db.get_progress(user_id)
            print(f"📊 Progress Data Retrieved: {progress_data}")

            print("🔄 Fetching personal records from database...")
            pr_data = await db.get_personal_records(user_id)
            print(f"🏋️ Personal Records Data Retrieved: {pr_data}")

            if not progress_data:
                print("❌ No progress data found for user.")
                await interaction.response.send_message(f"📊 {user_mention} has no progress data yet!")
                return

            # Fetch general progress values
            total_gym_checkins = progress_data["total_gym_checkins"] or 0
            total_food_logs = progress_data["total_food_logs"] or 0
            print(f"✅ Gym Check-ins: {total_gym_checkins}, Food Logs: {total_food_logs}")

            # Fetch weight change details
            print("🔄 Fetching weight change details...")
            first_weight, recent_weight, weight_change = await db.get_weight_change(user_id)
            print(f"⚖️ Weight Change Data - First: {first_weight}, Recent: {recent_weight}, Change: {weight_change}")

            if first_weight is not None and recent_weight is not None:
                trend = "🔼" if weight_change > 0 else "🔽" if weight_change < 0 else "⚖️"
                weight_display = f"{weight_change} lbs {trend} (**{recent_weight} lbs**)"
            else:
                weight_display = "⚖️ No weight change data"

            # Fetch PR rankings
            print("🔄 Fetching PR rankings...")
            rankings = await db.get_pr_rankings()
            print(f"🏆 PR Rankings Retrieved: {rankings}")

            def get_medal(lift_type):
                """Assigns ranking medals based on PR position"""
                sorted_prs = rankings.get(lift_type, [])
                for idx, (user, weight) in enumerate(sorted_prs[:8]):  # Top 8 users
                    if user == user_id:
                        return ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"][idx]
                return "🏆"  # Default if not in top 8

            # Extract PR values & assign ranking medals
            deadlift = pr_data["deadlift"] or 0 if pr_data else 0
            bench = pr_data["bench"] or 0 if pr_data else 0
            squat = pr_data["squat"] or 0 if pr_data else 0

            deadlift_medal = get_medal("deadlift")
            bench_medal = get_medal("bench")
            squat_medal = get_medal("squat")

            print(f"🏋️‍♂️ Deadlift PR: {deadlift} {deadlift_medal}, Bench PR: {bench} {bench_medal}, Squat PR: {squat} {squat_medal}")

            # Create **Page 1** Embed (General Progress)
            progress_embed = discord.Embed(
                title=f"📊 {target_user.display_name}'s Progress - (Page 1/2)",
                color=discord.Color.green()
            )
            progress_embed.add_field(name="💪 Gym Check-ins", value=f"{total_gym_checkins}", inline=True)
            progress_embed.add_field(name="🍽️ Food Logs", value=f"{total_food_logs}", inline=False)
            progress_embed.add_field(name="⚖️ Weight Change", value=weight_display, inline=False)
            progress_embed.set_footer(text="Page 1/2 - Click 'Next' for PRs")

            # Create **Page 2** Embed (PRs with Medals)
            pr_embed = discord.Embed(
                title=f"🏆 {target_user.display_name}'s Personal Records - (Page 2/2)",
                color=discord.Color.gold()
            )
            pr_embed.add_field(name="🏋️‍♂️ Deadlift PR", value=f"{deadlift} lbs {deadlift_medal}", inline=True)
            pr_embed.add_field(name="🏋️‍♂️ Bench Press PR", value=f"{bench} lbs {bench_medal}", inline=False)
            pr_embed.add_field(name="🏋️‍♀️ Squat PR", value=f"{squat} lbs {squat_medal}", inline=False)
            pr_embed.set_footer(text="Page 2/2 - Click 'Previous' for Check-ins")

            # Send response with View (Navigation Buttons)
            view = ProgressView(target_user, progress_embed, pr_embed)
            print(f"📤 Sending progress response to {interaction.user.name}")
            await interaction.response.send_message(embed=progress_embed, view=view)

        except Exception as e:
            print(f"❌ Error processing /progress command: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching your progress. Please try again later.")

async def setup(bot):
    await bot.add_cog(Progress(bot))
