import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os
import math

CHECKINS_PER_PAGE = 4
IMAGE_FOLDER = "checkin_images"


class ViewCheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="view_checkins", description="View your or another user's check-ins for gym, weight, or food.")
    @app_commands.describe(member="Mention a user to view their check-ins (leave blank to view yours)")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Gym 🏋️‍♂️", value="gym"),
            app_commands.Choice(name="Weight ⚖️", value="weight"),
            app_commands.Choice(name="Food 🍽️", value="food"),
        ]
    )
    async def view_checkins(self, interaction: discord.Interaction, category: app_commands.Choice[str], member: discord.Member = None):
        category = category.value
        target_user = member if member else interaction.user
        target_user_id = target_user.id

        await interaction.response.defer()

        checkins = await db.get_user_checkins(target_user_id, category)
        if not checkins:
            await interaction.followup.send(f"🚫 {target_user.mention} has no {category} check-ins yet!")
            return

        await self.send_checkin_page(interaction, checkins, page=0, category=category, target_user=target_user)

    async def send_checkin_page(self, interaction, checkins, page, category, target_user):
        try:
            total_pages = math.ceil(len(checkins) / CHECKINS_PER_PAGE)
            start_idx = page * CHECKINS_PER_PAGE
            end_idx = start_idx + CHECKINS_PER_PAGE
            checkins_on_page = checkins[start_idx:end_idx]

            embed = discord.Embed(
                title=f"📜 {target_user.display_name}'s {category.capitalize()} Check-Ins (Page {page + 1}/{total_pages})",
                color=discord.Color.blue()
            )

            image_files = []

            for idx, checkin in enumerate(checkins_on_page, start=start_idx + 1):
                timestamp = checkin["timestamp"].strftime("%Y-%m-%d %H:%M")
                details = f"**{timestamp}**\n"

                if category == "gym":
                    details += f"🏋️ **Workout:** {checkin['workout']}\n"
                elif category == "weight":
                    details += f"⚖️ **Weight:** {checkin['weight']} lbs\n"
                elif category == "food":
                    details += f"🍽️ **Meal:** {checkin['meal']}\n"

                embed.add_field(name="", value=details.strip(), inline=False)

                if checkin["image_path"] and os.path.exists(checkin["image_path"]):
                    file = discord.File(checkin["image_path"], filename=os.path.basename(checkin["image_path"]))
                    image_files.append(file)

            # Pagination
            view = None
            if total_pages > 1:
                view = PaginationButtons(self, checkins, page, category, target_user)

            # Add Back to Profile button
            combined_view = view or BackToProfileButton(target_user, interaction.client)
            if view:
                for item in BackToProfileButton(target_user, interaction.client).children:
                    combined_view.add_item(item)

            await interaction.edit_original_response(embed=embed, attachments=image_files, view=combined_view)

        except Exception as e:
            print(f"❌ Error in send_checkin_page: {e}")
            await interaction.followup.send(f"❌ An error occurred while displaying check-ins: {str(e)}")


class PaginationButtons(discord.ui.View):
    def __init__(self, cog, checkins, page, category, target_user):
        super().__init__(timeout=600)
        self.cog = cog
        self.checkins = checkins
        self.page = page
        self.category = category
        self.target_user = target_user

        self.previous.disabled = page == 0
        self.next.disabled = (page + 1) * CHECKINS_PER_PAGE >= len(checkins)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.send_checkin_page(interaction, self.checkins, self.page - 1, self.category, self.target_user)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.send_checkin_page(interaction, self.checkins, self.page + 1, self.category, self.target_user)


class BackToProfileButton(discord.ui.View):
    def __init__(self, user, bot):
        super().__init__(timeout=60)
        self.user = user
        self.bot = bot

    @discord.ui.button(label="🔙 Back to Profile", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            from commands.profile import generate_profile_embeds
            embed1, embed2, view = await generate_profile_embeds(self.user, self.bot, interaction)
            await interaction.response.edit_message(embed=embed1, view=view)
        except Exception as e:
            print("❌ Back to profile error:", e)
            try:
                await interaction.response.send_message("Something went wrong returning to profile.", ephemeral=True)
            except:
                pass

async def setup(bot):
    await bot.add_cog(ViewCheckIn(bot))
