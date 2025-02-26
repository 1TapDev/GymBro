import discord # Import the Discord API library
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from database import db
from scheduler import start_scheduler

load_dotenv()

class Client(commands.Bot): # Define a custom bot client class that inherits from discord.Client
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Allow bot to read message content
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self): # Proper way to load cogs in async bots
        print("🚀 Starting bot...")
        await db.connect()  # Connect to the database and confirm it worked
        for filename in os.listdir("./commands"):
            if filename.endswith(".py"):
                await self.load_extension(f"commands.{filename[:-3]}")

    async def on_ready(self):
        print(f'✅ Logged on as {self.user}!')
        await self.tree.sync()

        # Start APScheduler
        start_scheduler(self)
        print("⏰ APScheduler started: Weigh-In Reminder is active!")

    async def on_message(self, message):  # Prevents bot from responding to itself
        if message.author == self.user:
            return

    async def close(self):  # Close database connection when bot shuts down
        print("🔴 Shutting down bot...")
        await db.close()
        await super().close()

client = Client() # Create the bot instance

async def main():
    try:
        await client.start(os.getenv("TOKEN"))  # Run the bot with a token
    except KeyboardInterrupt:  # Handle Ctrl+C properly
        print("\n🛑 KeyboardInterrupt detected! Shutting down gracefully...")
        await client.close()  # Ensure database connection is closed
    finally:
        print("✅ Bot shutdown complete.")

# Run the bot with async event loop
asyncio.run(main())