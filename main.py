import discord # Import the Discord API library
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from database import db

load_dotenv()

class Client(commands.Bot): # Define a custom bot client class that inherits from discord.Client
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Allow bot to read message content
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self): # Proper way to load cogs in async bots
        for filename in os.listdir("./commands"):
            if filename.endswith(".py"):
                await self.load_extension(f"commands.{filename[:-3]}")

    async def on_ready(self): # Event that triggers when the bot successfully connects to Discord.
        print(f'Logged on as {self.user}!') # Print bot's username when connected
        await self.tree.sync()  # Sync slash commands

    async def on_message(self, message):  # Prevents bot from responding to itself
        if message.author == self.user:
            return

    async def close(self):  # Close database connection when bot shuts down
        await db.close()
        await super().close()

client = Client() # Create the bot instance

async def main():
    """Asynchronous function to initialize and run the bot with proper shutdown handling."""
    try:
        await client.start(os.getenv("TOKEN"))  # Run the bot with a token
    except KeyboardInterrupt:  # Handle Ctrl+C properly
        print("\n🛑 KeyboardInterrupt detected! Shutting down gracefully...")
        await client.close()  # Ensure database connection is closed
    finally:
        print("✅ Bot shutdown complete.")

# Run the bot with async event loop
asyncio.run(main())