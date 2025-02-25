import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os
import math
from PIL import Image  # Pillow for image resizing

# Constants
CHECKINS_PER_PAGE = 4
IMAGE_FOLDER = "checkin_images"
MAX_IMAGE_SIZE = (300, 300)  # Resize images to 300x300 pixels

class ViewCheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="view_checkins", description="View your past check-ins for gym, weight, or food.")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Gym 🏋️‍♂️", value="gym"),
            app_commands.Choice(name="Weight ⚖️", value="weight"),
            app_commands.Choice(name="Food 🍽️", value="food"),
        ]
    )
    async def view_checkins(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        category = category.value  # Get selected category
        user_id = interaction.user.id

        try:
            await interaction.response.defer()  # Prevents timeout

            # Fetch check-ins from the database
            checkins = await db.get_user_checkins(user_id, category)

            if not checkins:
                await interaction.followup.send(f"🚫 You have no {category} check-ins yet!")
                return

            # Start with page 1
            await self.send_checkin_page(interaction, checkins, page=0, category=category)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while fetching check-ins: {str(e)}")
            print(f"Error in view_checkins: {e}")  # Debugging output

    async def send_checkin_page(self, interaction, checkins, page, category):
        """Edits the original message to update the check-in page."""
        try:
            total_pages = math.ceil(len(checkins) / CHECKINS_PER_PAGE)
            start_idx = page * CHECKINS_PER_PAGE
            end_idx = start_idx + CHECKINS_PER_PAGE
            checkins_on_page = checkins[start_idx:end_idx]

            embed = discord.Embed(
                title=f"📜 {category.capitalize()} Check-Ins (Page {page+1}/{total_pages})",
                color=discord.Color.blue()
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

            image_files = []  # Store images for this page only

            for idx, checkin in enumerate(checkins_on_page, start=start_idx + 1):
                timestamp = checkin["timestamp"].strftime("%Y-%m-%d %H:%M")
                details = f"**{idx}. {timestamp}**\n"

                if category == "gym":
                    details += f"🏋️ **Workout:** {checkin['workout']}\n"
                elif category == "weight":
                    details += f"⚖️ **Weight:** {checkin['weight']} lbs\n"
                elif category == "food":
                    details += f"🍽️ **Meal:** {checkin['meal']}\n"

                embed.add_field(name="‎", value=details, inline=False)

                # Attach only the images for the current page
                if checkin["image_path"]:
                    image_path = checkin["image_path"]
                    if os.path.exists(image_path):
                        resized_image_path = self.resize_image(image_path)  # Resize image if needed
                        file = discord.File(resized_image_path, filename=os.path.basename(resized_image_path))
                        image_files.append(file)

            # Add pagination buttons if there are multiple pages
            view = None
            if total_pages > 1:
                view = PaginationButtons(self, checkins, page, category, interaction.user.id)

            # ✅ Use `edit_original_response()` to update message
            await interaction.edit_original_response(embed=embed, attachments=image_files, view=view)

        except Exception as e:
            print(f"Error in send_checkin_page: {e}")
            await interaction.followup.send(f"❌ An error occurred while displaying the check-ins: {str(e)}")

    def resize_image(self, image_path):
        """Resize image to fit within Discord's payload limits."""
        try:
            img = Image.open(image_path)
            img.thumbnail(MAX_IMAGE_SIZE)  # Resize while maintaining aspect ratio

            resized_path = image_path.replace(".jpg", "_small.jpg")
            img.save(resized_path, "JPEG", quality=85)  # Reduce quality slightly to save space

            return resized_path  # Return new file path
        except Exception as e:
            print(f"Error resizing image {image_path}: {e}")
            return image_path  # Fallback to original image if resizing fails

class PaginationButtons(discord.ui.View):
    """Handles pagination buttons for check-ins."""

    def __init__(self, cog, checkins, page, category, user_id):
        super().__init__(timeout=600)  # 10-minute timeout
        self.cog = cog
        self.checkins = checkins
        self.page = page
        self.category = category
        self.user_id = user_id  # Restrict button clicks to the original user

        # Enable or disable buttons based on current page
        self.previous.disabled = page == 0
        self.next.disabled = (page + 1) * CHECKINS_PER_PAGE >= len(checkins)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensures only the command user can navigate the pages."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("🚫 You can only navigate your own check-ins!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, custom_id="prev_page")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles Previous Page button."""
        await interaction.response.defer()  # Defer to prevent timeout
        await self.cog.send_checkin_page(interaction, self.checkins, self.page - 1, self.category)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles Next Page button."""
        await interaction.response.defer()  # Defer to prevent timeout
        await self.cog.send_checkin_page(interaction, self.checkins, self.page + 1, self.category)

async def setup(bot):
    await bot.add_cog(ViewCheckIn(bot))
