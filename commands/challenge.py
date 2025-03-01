import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from database import db
from datetime import datetime, timedelta


class Challenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_challenge = None  # Store active challenge info

    @app_commands.command(name="challenge", description="Start a new challenge!")
    async def challenge(self, interaction: discord.Interaction, days: int, message: str):
        print("[DEBUG] Received /challenge start command")

        # Defer response
        await interaction.response.defer()
        print("[DEBUG] Interaction response deferred.")

        if self.active_challenge:
            print("[DEBUG] Challenge already active, denying request.")
            await interaction.followup.send(
                "⚠️ A challenge is already active! Wait for it to finish before starting a new one.", ephemeral=True)
            return

        # ✅ Correctly calculate 'end_date' inside the function
        end_date = datetime.utcnow() + timedelta(days=days)
        print(f"[DEBUG] Challenge end date set to: {end_date}")

        # Store challenge details in DB
        try:
            print("[DEBUG] Challenge end date calculation successful.")
            async with db.pool.acquire() as conn:
                print("[DEBUG] Acquired database connection.")
                await conn.execute("""
                    INSERT INTO challenges (user_id, username, start_date, end_date, status)
                    VALUES ($1, $2, NOW(), $3, 'active')
                """, interaction.user.id, interaction.user.name, end_date)
                print("[DEBUG] Challenge successfully inserted into database.")

                # Retrieve the challenge ID
                challenge_id = await conn.fetchval(
                    "SELECT id FROM challenges WHERE user_id = $1 ORDER BY start_date DESC LIMIT 1",
                    interaction.user.id
                )
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            return

        print("[DEBUG] Preparing challenge message.")
        embed = discord.Embed(
            title="🏆 New Challenge Started!",
            description=f"📅 **Duration:** {days} Days\n📢 **Goal:** {message}\n✅ **React to Join!**",
            color=discord.Color.gold()
        )

        try:
            challenge_message = await interaction.channel.send(embed=embed)
            print("[DEBUG] Challenge message sent.")
            await challenge_message.add_reaction("✅")
            print("[DEBUG] Reaction added to challenge message.")
            await interaction.followup.send("✅ Challenge created successfully! Users can now join.", ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Failed to send challenge message: {e}")
            await interaction.followup.send("❌ Error sending challenge message.", ephemeral=True)
            return

        self.active_challenge = {
            "id": challenge_id,
            "message": message,
            "end_date": end_date,
            "participants": []
        }

        # Wait for reactions
        def check(reaction, user):
            return reaction.message.id == challenge_message.id and str(reaction.emoji) == "✅" and not user.bot

        while True:
            try:
                print("[DEBUG] Waiting for users to react to join challenge...")
                reaction, user = await self.bot.wait_for("reaction_add", timeout=86400 * days, check=check)
                print(f"[DEBUG] User {user.name} joined challenge.")
                self.active_challenge["participants"].append(user.id)
                await self.register_user(user)
            except asyncio.TimeoutError:
                print("[DEBUG] Challenge duration ended, stopping reaction collection.")
                break  # Challenge ended

        self.active_challenge = None  # Reset challenge

    async def register_user(self, user):
        """Registers a user in the challenge_participants table and asks for weight/goal."""
        print(f"[DEBUG] Sending registration DM to {user.name}")
        dm_channel = await user.create_dm()
        await dm_channel.send("🏆 Welcome to the challenge! Let's get started.")

        # Ask for weight
        await dm_channel.send("⚖️ Please enter your current weight:")
        msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel)
        current_weight = float(msg.content)

        # Ask for goal weight
        await dm_channel.send("🎯 Please enter your goal weight:")
        msg = await self.bot.wait_for("message", check=lambda m: m.author == user and m.channel == dm_channel)
        goal_weight = float(msg.content)

        # Store user details in database
        try:
            async with db.pool.acquire() as conn:
                print(f"[DEBUG] Registering {user.name} in challenge_participants.")
                await conn.execute("""
                    INSERT INTO challenge_participants (challenge_id, user_id, username, current_weight, goal_weight)
                    VALUES ($1, $2, $3, $4, $5)
                """, self.active_challenge["id"], user.id, user.name, current_weight, goal_weight)
                print("[DEBUG] Successfully registered participant.")
                await dm_channel.send("✅ You have been successfully registered in the challenge!")
        except Exception as e:
            print(f"[ERROR] Failed to register participant: {e}")
            await dm_channel.send("❌ Error joining the challenge.")
            return


async def setup(bot):
    await bot.add_cog(Challenge(bot))
