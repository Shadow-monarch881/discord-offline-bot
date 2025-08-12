import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio

OWNER_ID = 620819429139415040
TOKEN = os.getenv("Secret_Key") or "YOUR_BOT_TOKEN_HERE"
GUILD_ID = 1116737021470314597

allowed_servers = set([GUILD_ID])

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def is_allowed_server_or_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == OWNER_ID:
            return True
        if interaction.guild and interaction.guild.id in allowed_servers:
            return True
        print(f"[DENIED] User {interaction.user} in guild {interaction.guild.id} tried command.")
        await interaction.response.send_message("❌ This server is not allowed to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Synced commands on guild {GUILD_ID}")
    for guild_id in allowed_servers:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
            print(f"Synced commands on guild {guild_id}")
        except Exception as e:
            print(f"Failed to sync commands on guild {guild_id}: {e}")

@bot.tree.command(name="hello", description="Say hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.display_name}!")

@bot.tree.command(name="access", description="Owner only: allow new guild")
@app_commands.describe(server_id="Server ID to allow")
@is_allowed_server_or_owner()
async def access(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        guild_id = int(server_id)
    except:
        await interaction.response.send_message("❌ Invalid guild ID.", ephemeral=True)
        return
    if guild_id in allowed_servers:
        await interaction.response.send_message(f"Guild {guild_id} already allowed.", ephemeral=True)
        return
    allowed_servers.add(guild_id)
    try:
        await bot.tree.sync(guild=discord.Object(id=guild_id))
        await interaction.response.send_message(f"✅ Access granted and commands synced for guild {guild_id}.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to sync commands: {e}", ephemeral=True)

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
