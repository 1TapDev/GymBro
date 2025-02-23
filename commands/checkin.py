import discord  # Import the Discord API library
from discord import app_commands
from discord.ext import commands
import asyncio
import hashlib  # Used for detecting reused images
from database import db

class CheckIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_images = {}  # Store image hashes per user to prevent abuse

    def hash_image(self, image_bytes):
        return hashlib.md5(image_bytes).hexdigest()  # Generates a hash for the image

    @app_commands.command(name="checkin", description="Log a check-in for gym, weight, or food.")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Gym 🏋️‍♂️", value="gym"),
            app_commands.Choice(name="Weight ⚖️", value="weight"),
            app_commands.Choice(name="Food 🍽️", value="food"),
        ]
    )
    async def checkin(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        category = category.value
        user_id = interaction.user.id
        username = interaction.user.name
        print(f"📥 Received /checkin command from {username} (ID: {user_id}) - Category: {category}")

        # Acknowledge the command immediately
        await interaction.response.defer()
        print("✅ Response deferred.")

        try:
            print("📝 Adding user to database...")
            await db.add_user(user_id, username)
            print("✅ User added to database.")

            print("📝 Logging check-in in database...")
            await db.log_checkin(user_id, category, None)
            print("✅ Check-in logged successfully.")

            await interaction.followup.send(
                f"✅ **{category.capitalize()} check-in started!** Please upload a photo."
            )
            print("📩 Follow-up message sent! Waiting for user image...")

        except Exception as e:
            print(f"❌ Database error: {e}")
            await interaction.followup.send("❌ An error occurred while logging your check-in. Please try again.")
            return

        def check(m):
            return m.author.id == interaction.user.id and m.attachments  # Check if user sends an image

        try:
            print("⏳ Waiting for user to upload an image...")
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
            print("📷 Image received! Processing...")

            attachment = message.attachments[0]

            if not attachment.content_type.startswith("image/"):
                await interaction.followup.send("❌ That’s not an image! Please upload a valid photo.")
                return

            image_bytes = await attachment.read()
            image_hash = self.hash_image(image_bytes)
            print(f"🔍 Image hashed: {image_hash}")

            # Ensure user doesn't reuse the same image
            async with db.pool.acquire() as conn:
                existing_checkin = await conn.fetchrow("""
                    SELECT * FROM checkins WHERE user_id = $1 AND image_hash = $2
                """, user_id, image_hash)

            if existing_checkin:
                await interaction.followup.send(
                    "⚠️ You have already used this image for a check-in. Please upload a new one.")
                return

            # Log the check-in with image hash
            await db.log_checkin(user_id, category, image_hash)
            await interaction.followup.send(f"✅ {category.capitalize()} check-in **completed!** You earned 1 point.")

        except asyncio.TimeoutError:
            await interaction.followup.send("⏳ You took too long to upload an image. Please try again.")
            print("❌ Timeout! User didn't upload an image.")

        except Exception as e:
            print(f"❌ Error processing image: {e}")
            await interaction.followup.send("❌ An unexpected error occurred. Please try again.")


async def setup(bot):
    await bot.add_cog(CheckIn(bot))