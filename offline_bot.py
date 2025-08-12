import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import timedelta, datetime
import webserver  # Your webserver module

# === CONFIG ===
OWNER_ID = 620819429139415040  # Your Discord user ID (Superior Owner)
TOKEN = os.getenv("Secret_Key") or "YOUR_BOT_TOKEN_HERE"
GUILD_ID = 1116737021470314597  # Your main server ID for initial sync

# Start Flask webserver (if you have one)
webserver.start()

# === Intents & Bot Setup ===
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Role hierarchy (highest to lowest)
ROLES_HIERARCHY = [
    "owner",
    "co-owner",
    "head admin",
    "admin",
    "head mod",
    "mod",
    "moderator"
]

# Globals
last_record = ""
repeat_enabled = False
repeat_channel_id = None
allowed_servers = set([GUILD_ID])  # Starts with your main server allowed
allowed_channels = set()
sleep_start_times = {}

# Helper: Permission check decorator for allowed servers + owner
def is_allowed_server_or_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == OWNER_ID:
            return True
        if interaction.guild and interaction.guild.id in allowed_servers:
            return True
        await interaction.response.send_message("❌ This server is not allowed to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# Role utility functions
def get_highest_role_index(member: discord.Member):
    if member.id == OWNER_ID:
        return 0
    member_roles = [r.name.lower() for r in member.roles]
    indices = [ROLES_HIERARCHY.index(r) for r in member_roles if r in ROLES_HIERARCHY]
    if indices:
        return min(indices)  # Lower index = higher role
    if member == member.guild.owner:
        return 0
    return len(ROLES_HIERARCHY) + 1

def has_required_role(member: discord.Member, required_role: str):
    required_index = ROLES_HIERARCHY.index(required_role.lower())
    member_index = get_highest_role_index(member)
    return member_index <= required_index

def has_privileged_role(member: discord.Member):
    if member.id == OWNER_ID:
        return True
    member_roles = {r.name.lower() for r in member.roles}
    allowed = {"mod", "head mod", "admin", "head admin", "co-owner", "owner"}
    return any(role in member_roles for role in allowed)

def has_admin_role(member: discord.Member):
    if member.id == OWNER_ID:
        return True
    member_roles = {r.name.lower() for r in member.roles}
    allowed = {"admin", "head admin", "co-owner", "owner"}
    return any(role in member_roles for role in allowed)

# === Owner-only commands ===

@bot.tree.command(name="access", description="Owner only: Allow a server ID for commands")
@app_commands.describe(server_id="Server ID to allow access")
@is_allowed_server_or_owner()
async def access_cmd(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        guild_id = int(server_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid server ID.", ephemeral=True)
        return

    if guild_id in allowed_servers:
        await interaction.response.send_message(f"✅ Server ID {guild_id} is already allowed.", ephemeral=True)
        return

    allowed_servers.add(guild_id)
    # Sync commands to new server
    await bot.tree.sync(guild=discord.Object(id=guild_id))
    await interaction.response.send_message(f"✅ Access granted for server ID {guild_id}.")

@bot.tree.command(name="allowchannel", description="Owner only: Allow current channel for commands")
@is_allowed_server_or_owner()
async def allowchannel_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    allowed_channels.add(interaction.channel_id)
    await interaction.response.send_message(f"✅ Channel <#{interaction.channel_id}> allowed for commands.")

# === Moderation commands ===

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for kicking")
@is_allowed_server_or_owner()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member} was kicked. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot kick this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason for banning")
@is_allowed_server_or_owner()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member} was banned. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot ban this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Unban a user")
@app_commands.describe(user="User to unban")
@is_allowed_server_or_owner()
async def unban(interaction: discord.Interaction, user: discord.User):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"♻️ {user} has been unbanned.")
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found in ban list.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Timeout a member")
@app_commands.describe(member="Member to mute", duration="Duration in minutes", reason="Reason for muting")
@is_allowed_server_or_owner()
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    until = discord.utils.utcnow() + timedelta(minutes=duration)
    try:
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"🔇 {member} muted for {duration} minutes. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot timeout this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Remove timeout from a member")
@app_commands.describe(member="Member to unmute")
@is_allowed_server_or_owner()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 {member} has been unmuted.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# === Role Management commands ===

@bot.tree.command(name="promote", description="Promote a member to the next higher role")
@app_commands.describe(member="Member to promote")
@is_allowed_server_or_owner()
async def promote(interaction: discord.Interaction, member: discord.Member):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    member_roles = [r.name.lower() for r in member.roles]
    for i in reversed(range(len(ROLES_HIERARCHY) - 1)):
        if ROLES_HIERARCHY[i + 1] in member_roles:
            new_role = discord.utils.get(interaction.guild.roles, name=ROLES_HIERARCHY[i])
            old_role = discord.utils.get(interaction.guild.roles, name=ROLES_HIERARCHY[i + 1])
            if new_role and old_role:
                await member.remove_roles(old_role)
                await member.add_roles(new_role)
                await interaction.response.send_message(f"⬆️ {member} promoted to {new_role.name}.")
                return
    await interaction.response.send_message("⚠️ This member cannot be promoted further.", ephemeral=True)

@bot.tree.command(name="demote", description="Demote a member to the next lower role")
@app_commands.describe(member="Member to demote")
@is_allowed_server_or_owner()
async def demote(interaction: discord.Interaction, member: discord.Member):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return

    member_roles = [r.name.lower() for r in member.roles]
    for i in range(len(ROLES_HIERARCHY) - 1):
        if ROLES_HIERARCHY[i] in member_roles:
            new_role = discord.utils.get(interaction.guild.roles, name=ROLES_HIERARCHY[i + 1])
            old_role = discord.utils.get(interaction.guild.roles, name=ROLES_HIERARCHY[i])
            if new_role and old_role:
                await member.remove_roles(old_role)
                await member.add_roles(new_role)
                await interaction.response.send_message(f"⬇️ {member} demoted to {new_role.name}.")
                return
    await interaction.response.send_message("⚠️ This member cannot be demoted further.", ephemeral=True)

# === Offline utility commands (Mods+) ===

@bot.tree.command(name="record", description="Save a record (Mods & above)")
@app_commands.describe(text="Text to save as record")
@is_allowed_server_or_owner()
async def record_cmd(interaction: discord.Interaction, text: str):
    global last_record
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    last_record = text
    await interaction.response.send_message(f"✅ Record saved: {text}")

@bot.tree.command(name="print", description="Print the last record (Mods & above)")
@is_allowed_server_or_owner()
async def print_cmd(interaction: discord.Interaction):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.send_message(f"📝 Last record: {last_record or 'No record saved.'}")

@bot.tree.command(name="repeat", description="Toggle repeating the last record in this channel (Mods & above)")
@is_allowed_server_or_owner()
async def repeat_cmd(interaction: discord.Interaction):
    global repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    repeat_enabled = not repeat_enabled
    repeat_channel_id = interaction.channel_id if repeat_enabled else None
    await interaction.response.send_message(f"🔁 Repeat mode {'enabled' if repeat_enabled else 'disabled'} in this channel.")

@bot.tree.command(name="stop", description="Stop repeat mode manually (Mods & above)")
@is_allowed_server_or_owner()
async def stop_cmd(interaction: discord.Interaction):
    global repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    repeat_enabled = False
    repeat_channel_id = None
    await interaction.response.send_message("🛑 Repeat mode manually stopped.")

@bot.tree.command(name="refresh", description="Erase the saved record and stop repeat (Mods & above)")
@is_allowed_server_or_owner()
async def refresh_cmd(interaction: discord.Interaction):
    global last_record, repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    last_record = ""
    repeat_enabled = False
    repeat_channel_id = None
    await interaction.response.send_message("♻️ Record cleared and repeat mode disabled.")

# === Sleep commands (Admins+) ===

@bot.tree.command(name="sleep", description="Start your sleep timer and say good night (Admins+ only)")
@is_allowed_server_or_owner()
async def sleep_cmd(interaction: discord.Interaction):
    if not has_admin_role(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    sleep_start_times[interaction.user.id] = datetime.utcnow()
    await interaction.response.send_message(f"😴 Good night, {interaction.user.display_name}! Sleep well tonight.")

@bot.tree.command(name="sleeping", description="List users currently sleeping (Admins+ only)")
@is_allowed_server_or_owner()
async def sleeping_cmd(interaction: discord.Interaction):
    if not has_admin_role(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    if not sleep_start_times:
        await interaction.response.send_message("Nobody is currently sleeping.")
        return
    users = []
    for user_id in sleep_start_times.keys():
        user = bot.get_user(user_id)
        users.append(user.display_name if user else f"User ID {user_id}")
    await interaction.response.send_message("💤 Currently sleeping users:\n" + "\n".join(users))

# === Info commands ===

@bot.tree.command(name="server_rules", description="Show Akane's usage rules for the server")
@is_allowed_server_or_owner()
async def server_rules_cmd(interaction: discord.Interaction):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📜 Akane Bot Rules & Commands",
        description="Akane bot has a **Superior Owner**, Role hierarchy, and commands for moderation, utilities, and info.",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="👑 Superior Owner",
        value=f"User ID: {OWNER_ID}\nHas the highest permission above all roles.",
        inline=False
    )

    embed.add_field(
        name="🛡️ Role Hierarchy (Highest to Lowest)",
        value="Owner > Co-owner > Head Admin > Admin > Head Mod > Mod > Moderator",
        inline=False
    )

    embed.add_field(
        name="⚙️ Moderation Commands",
        value=(
            "/kick member:@User reason:<text> — Kick a member (Mods+)\n"
            "/ban member:@User reason:<text> — Ban a member (Admins+)\n"
            "/unban user:User#1234 — Unban a user (Admins+)\n"
            "/mute member:@User duration:<minutes> reason:<text> — Timeout a member (Mods+)\n"
            "/unmute member:@User — Remove timeout (Mods+)"
        ),
        inline=False
    )

    embed.add_field(
        name="🔧 Role Management Commands",
        value=(
            "/promote member:@User — Promote to next higher role (Admins+)\n"
            "/demote member:@User — Demote to next lower role (Admins+)"
        ),
        inline=False
    )

    embed.add_field(
        name="📝 Offline Utility Commands (Mods+)",
        value=(
            "/record text:<text> — Save a record\n"
            "/print — Show last saved record\n"
            "/repeat — Toggle repeating last record in channel\n"
            "/stop — Stop repeating last record\n"
            "/refresh — Clear record and stop repeat"
        ),
        inline=False
    )

    embed.add_field(
        name="😴 Sleep Commands (Admins+)",
        value=(
            "/sleep — Start sleep timer\n"
            "/sleeping — List currently sleeping users"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Owner-only Commands",
        value=(
            "/allowchannel — Allow current channel for commands\n"
            "/access server_id:<id> — Allow server ID for cross-server access"
        ),
        inline=False
    )

    embed.add_field(
        name="ℹ️ Info Commands (Mods+)",
        value=(
            "/server_rules — Show this rules & commands list\n"
            "/about — About Akane bot"
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Rules",
        value=(
            "1️⃣ Superior Owner has full control.\n"
            "2️⃣ Use commands respectfully.\n"
            "3️⃣ Follow server rules and hierarchy.\n"
            "4️⃣ Offline utility commands only work when owner's PC is on.\n"
            "5️⃣ Only authorized roles may use moderation and utility commands."
        ),
        inline=False
    )

    embed.set_footer(text="Stay respectful and enjoy chatting with Akane 💜")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="about", description="Learn about Akane")
@is_allowed_server_or_owner()
async def about_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✨ About Akane",
        description="Always happy to help you 💖",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="💡 Creator",
        value="Made with love by **Noviac** for this server.",
        inline=False
    )
    embed.add_field(
        name="🌐 Community",
        value="[Join here!](https://discord.gg/HgZP7tMw)",
        inline=False
    )
    embed.add_field(
        name="📩 Contact",
        value="For further questions, please DM **Noviac**.",
        inline=False
    )
    embed.set_footer(text="😊 Have a nice day! 🌸")
    await interaction.response.send_message(embed=embed)

# === Repeat listener and sleep wakeup ===

@bot.event
async def on_message(message):
    global repeat_enabled, last_record, repeat_channel_id
    if message.author.bot:
        return

    # Repeat last record if enabled and in the right channel
    if repeat_enabled and last_record and message.channel.id == repeat_channel_id:
        await message.channel.send(last_record)

    # Sleep wake-up message
    user_id = message.author.id
    if user_id in sleep_start_times:
        sleep_start = sleep_start_times.pop(user_id)
        sleep_duration = datetime.utcnow() - sleep_start

        hours = sleep_duration.seconds // 3600
        minutes = (sleep_duration.seconds % 3600) // 60

        time_str = ""
        if hours > 0:
            time_str += f"{hours} hour{'s' if hours != 1 else ''} "
        if minutes > 0 or hours == 0:
            time_str += f"{minutes} minute{'s' if minutes != 1 else ''}"

        await message.channel.send(f"🌞 Welcome back, {message.author.display_name}! You slept for {time_str.strip()}.")

    await bot.process_commands(message)

# === On ready: sync commands for allowed servers ===

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    # Sync commands on main guild first
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    # Sync commands on all allowed servers
    for guild_id in allowed_servers:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
            print(f"🔄 Commands synced for guild {guild_id}")
        except Exception as e:
            print(f"❌ Failed to sync commands for guild {guild_id}: {e}")

# === Run bot ===

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()
