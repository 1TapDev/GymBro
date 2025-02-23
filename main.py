import discord # Import the Discord API library
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

class Client(commands.Bot): # Define a custom bot client class that inherits from discord.Client
    async def on_ready(self): # Event that triggers when the bot successfully connects to Discord.
        print(f'Logged on as {self.user}!') # Print bot's username when connected

    async def on_message(self, message):
        if message.author == self.user:
            return

# Set up bot intents (permissions for events the bot can access).
intents = discord.Intents.default()
intents.message_content = True # Allow bot to read message content
client = Client(command_prefix="!", intents=intents)

@client.tree.command(name="checkin", description="Submit a gym check-in to earn points.")
async def checkin(interaction: discord.Interaction):
    await interaction.response.send_message()

client.run(os.environ.get("token")) # Run the bot with a token
