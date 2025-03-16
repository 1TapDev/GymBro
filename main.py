import discord  # Import the Discord API library
import os
import asyncio
from discord.ext import commands, tasks  # Add tasks for background looping
from dotenv import load_dotenv
from database import db
from scheduler import start_scheduler  # Import the scheduler

load_dotenv()

class Client(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Allow bot to read messages
        intents.reactions = True  # ✅ REQUIRED for detecting reactions
        intents.guilds = True
        intents.members = True  # REQUIRED if checking users in guild
        super().__init__(command_prefix="!", intents=intents)
        self.presence_task_running = False  # Prevent multiple loop starts

    async def setup_hook(self):
        print("🚀 Starting bot...")
        await db.connect()  # Connect to the database and confirm it worked
        for filename in os.listdir("./commands"):
            if filename.endswith(".py"):
                await self.load_extension(f"commands.{filename[:-3]}")

    async def on_ready(self):
        print(f'✅ Logged on as {self.user}!')
        await self.tree.sync()

        # **Start APScheduler**
        start_scheduler(self)
        print("⏰ APScheduler started: Weigh-In Reminder is active!")

        # ✅ Set initial presence
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Gym Check-ins 🏋️‍♂️"
        ))
        print("🎮 Rich Presence set: Watching Gym Check-ins 🏋️‍♂️")

        # ✅ Start rich presence loop only once
        if not self.presence_task_running:
            print("🔄 [Presence] Starting presence task loop...")
            self.presence_task.start()
            self.presence_task_running = True
        else:
            print("⚠️ [Presence] Presence task is already running.")

    @tasks.loop(minutes=5)  # ✅ Reapply presence every 5 minutes
    async def presence_task(self):
        if self.is_ready():
            print("🔄 [Presence] Updating bot activity...")
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name="Gym Check-ins 🏋️‍♂️"
            )
            await self.change_presence(activity=activity)
            print("✅ [Presence] Activity updated successfully.")

    async def close(self):
        print("🔴 Shutting down bot...")
        self.presence_task.cancel()  # ✅ Stop presence task before shutdown
        await db.close()
        await super().close()

client = Client()

async def main():
    try:
        await client.start(os.getenv("TOKEN"))  # Run the bot with a token
    except KeyboardInterrupt:
        print("\n🛑 KeyboardInterrupt detected! Shutting down gracefully...")
        await client.close()
    finally:
        print("✅ Bot shutdown complete.")

# Run the bot
asyncio.run(main())
