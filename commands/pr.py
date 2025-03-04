import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import os
import uuid
from database import db

PR_VIDEO_FOLDER = "pr_videos"

class PRConfirmationView(View):
    def __init__(self, user_id, lift, new_value, current_value, interaction):
        super().__init__()
        self.user_id = user_id
        self.lift = lift
        self.new_value = new_value
        self.current_value = current_value
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ You can't confirm someone else's PR!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Yes", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        try:
            print(f"[DEBUG] Updating PR: User {self.user_id}, Lift {self.lift}, New PR {self.new_value}")
            await db.update_pr(self.user_id, self.lift, self.new_value)  # ✅ Now correctly calls class method

            embed = discord.Embed(
                title="✅ PR Updated!",
                description=f"Your **{self.lift.capitalize()} PR** has been set to **{self.new_value} lbs**!",
                color=discord.Color.green()
            )
            embed.set_footer(text="Now upload a video of your PR attempt (Max 30s).")
            await interaction.response.edit_message(embed=embed, view=None)

            await self.prompt_video_upload(interaction)

        except Exception as e:
            print(f"[ERROR] Failed to update PR: {e}")
            await interaction.response.send_message("❌ Error updating PR. Please try again.", ephemeral=True)

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="❌ PR Update Canceled",
            description="Your PR remains unchanged.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def prompt_video_upload(self, interaction: discord.Interaction):
        await interaction.followup.send("✅ Please upload a **video (max 60s)** of your PR attempt.")

        def check(m):
            return m.author.id == self.user_id and m.attachments and m.attachments[0].content_type.startswith("video/")

        try:
            message = await interaction.client.wait_for("message", timeout=240.0, check=check)
            attachment = message.attachments[0]

            user_uuid = str(uuid.uuid4())
            user_folder = os.path.join(PR_VIDEO_FOLDER, str(self.user_id))
            os.makedirs(user_folder, exist_ok=True)

            video_path = os.path.join(user_folder, f"{user_uuid}.mp4")
            await attachment.save(video_path)

            await db.save_pr_video(self.user_id, self.lift, video_path)
            await interaction.followup.send("✅ PR video saved successfully!")

        except Exception as e:
            await interaction.followup.send("❌ Failed to upload PR video. Please try again.")
            print(f"[ERROR] PR video upload failed: {e}")

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
