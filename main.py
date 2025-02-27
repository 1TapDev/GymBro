import discord # Import the Discord API library
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from database import db
from scheduler import start_scheduler  # Import the scheduler

load_dotenv()

class Client(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Allow bot to read message content
        super().__init__(command_prefix="!", intents=intents)

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

    async def close(self):
        print("🔴 Shutting down bot...")
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
