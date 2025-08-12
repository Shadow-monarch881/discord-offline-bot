import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import timedelta, datetime
import webserver  # your webserver import

# === CONFIG ===
OWNER_ID = 620819429139415040  # Your Discord user ID
TOKEN = os.getenv("Secret_Key") or "YOUR_DISCORD_BOT_TOKEN_HERE"
GUILD_ID = 1116737021470314597  # Your server ID for guild command sync

# Start Flask webserver in background thread
webserver.start()

# === Intents & Bot setup ===
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

# === Globals for offline utility & sleep feature ===
last_record = ""
repeat_enabled = False
repeat_channel_id = None

allowed_channels = set()  # Channels allowed for commands (set by /allowchannel)
allowed_servers = set()   # Servers allowed for cross-server access (set by /access)

sleep_start_times = {}  # user_id -> datetime when /sleep was used

# === Utility functions ===

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
    # Used for commands allowed for mod and above (mod+)
    if member.id == OWNER_ID:
        return True
    member_roles = {r.name.lower() for r in member.roles}
    allowed = {"mod", "head mod", "admin", "head admin", "co-owner", "owner"}
    return any(role in member_roles for role in allowed)

def has_admin_role(member: discord.Member):
    # Admin and above
    if member.id == OWNER_ID:
        return True
    member_roles = {r.name.lower() for r in member.roles}
    allowed = {"admin", "head admin", "co-owner", "owner"}
    return any(role in member_roles for role in allowed)


# === Moderation Commands ===

@bot.tree.command(name="kick", description="Kick a member from the server", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to kick", reason="Reason for kicking")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member} was kicked. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot kick this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member from the server", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to ban", reason="Reason for banning")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member} was banned. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot ban this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Unban a user", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="User to unban")
async def unban(interaction: discord.Interaction, user: discord.User):
    if not has_required_role(interaction.user, "admin"):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"♻️ {user} has been unbanned.")
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found in ban list.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Timeout a member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to mute", duration="Duration in minutes", reason="Reason for muting")
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "No reason provided"):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    until = discord.utils.utcnow() + timedelta(minutes=duration)
    try:
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"🔇 {member} muted for {duration} minutes. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot timeout this member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Remove timeout from a member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 {member} has been unmuted.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# === Role Management Commands ===

@bot.tree.command(name="promote", description="Promote a member to the next higher role", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to promote")
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

@bot.tree.command(name="demote", description="Demote a member to the next lower role", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to demote")
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

# === Offline Utility Commands ===

@bot.tree.command(name="record", description="Save a record (Mods & above)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(text="Text to save as record")
async def record_cmd(interaction: discord.Interaction, text: str):
    global last_record
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    last_record = text
    await interaction.response.send_message(f"✅ Record saved: {text}")

@bot.tree.command(name="print", description="Print the last record (Mods & above)", guild=discord.Object(id=GUILD_ID))
async def print_cmd(interaction: discord.Interaction):
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.send_message(f"📝 Last record: {last_record or 'No record saved.'}")

@bot.tree.command(name="repeat", description="Toggle repeating the last record in this channel (Mods & above)", guild=discord.Object(id=GUILD_ID))
async def repeat_cmd(interaction: discord.Interaction):
    global repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    repeat_enabled = not repeat_enabled
    repeat_channel_id = interaction.channel_id if repeat_enabled else None
    await interaction.response.send_message(f"🔁 Repeat mode {'enabled' if repeat_enabled else 'disabled'} in this channel.")

@bot.tree.command(name="stop", description="Stop repeat mode manually (Mods & above)", guild=discord.Object(id=GUILD_ID))
async def stop_cmd(interaction: discord.Interaction):
    global repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    repeat_enabled = False
    repeat_channel_id = None
    await interaction.response.send_message("🛑 Repeat mode manually stopped.")

@bot.tree.command(name="refresh", description="Erase the saved record and stop repeat (Mods & above)", guild=discord.Object(id=GUILD_ID))
async def refresh_cmd(interaction: discord.Interaction):
    global last_record, repeat_enabled, repeat_channel_id
    if not has_required_role(interaction.user, "mod"):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    last_record = ""
    repeat_enabled = False
    repeat_channel_id = None
    await interaction.response.send_message("♻️ Record cleared and repeat mode disabled.")

# === Sleep / AllowChannel / Access Commands ===

# Owner-only: Allow current channel for sleep commands for members below mod+
@bot.tree.command(name="allowchannel", description="Owner only: Allow current channel for members to use sleep")
async def allowchannel_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    allowed_channels.add(interaction.channel_id)
    await interaction.response.send_message(f"✅ Channel <#{interaction.channel_id}> allowed for members to use sleep commands.")

# Owner-only: Allow server id for cross-server commands (you can expand usage)
@bot.tree.command(name="access", description="Owner only: Allow a server ID for cross-server access")
@app_commands.describe(server_id="Server ID to allow access")
async def access_cmd(interaction: discord.Interaction, server_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    try:
        allowed_servers.add(int(server_id))
        await interaction.response.send_message(f"✅ Access granted for server ID {server_id}.")
    except ValueError:
        await interaction.response.send_message("❌ Invalid server ID.", ephemeral=True)

# Sleep command: mods+ anywhere OR members in allowed channels only
@bot.tree.command(name="sleep", description="Start your sleep timer")
async def sleep_cmd(interaction: discord.Interaction):
    user = interaction.user
    if not has_privileged_role(user) and interaction.channel_id not in allowed_channels:
        await interaction.response.send_message("❌ You can only use this command in allowed channels.", ephemeral=True)
        return
    sleep_start_times[user.id] = datetime.utcnow()
    await interaction.response.send_message(f"😴 {user.mention}, you are now marked as sleeping. Sweet dreams!")

# Sleeping list command (admins+)
@bot.tree.command(name="sleeping", description="Show list of sleeping users (Admins+ only)", guild=discord.Object(id=GUILD_ID))
async def sleeping_cmd(interaction: discord.Interaction):
    if not has_admin_role(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    if not sleep_start_times:
        await interaction.response.send_message("Nobody is currently sleeping.")
        return
    mentions = []
    for user_id in sleep_start_times.keys():
        user = bot.get_user(user_id)
        mentions.append(user.mention if user else f"<@{user_id}>")
    await interaction.response.send_message(f"😴 Currently sleeping: {', '.join(mentions)}")

# === Info Commands ===

@bot.tree.command(name="server_rules", description="Show Akane's usage rules for the server", guild=discord.Object(id=GUILD_ID))
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

# --- About command (GLOBAL) ---
@bot.tree.command(name="about", description="Learn about Akane")
async def about_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Akane Bot", description="Hello! I am Akane, your friendly moderation and utility bot. 💜", color=discord.Color.purple())
    embed.add_field(name="Owner", value=f"<@{OWNER_ID}>", inline=True)
    embed.add_field(name="Commands", value="Moderation, Role Management, Offline Utility, Sleep, Info, and Owner commands.", inline=False)
    embed.set_footer(text="Made with love ❤️")
    await interaction.response.send_message(embed=embed)

# === Events ===

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    # Sync guild commands for faster updates in guild
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    # Sync global commands like /about
    await bot.tree.sync()
    print("🔄 Commands synced.")

@bot.event
async def on_message(message: discord.Message):
    global last_record, repeat_enabled, repeat_channel_id
    if message.author == bot.user:
        return

    # Wake up user on any message if sleeping
    if message.author.id in sleep_start_times:
        del sleep_start_times[message.author.id]
        await message.channel.send(f"🌞 Welcome back, {message.author.mention}!")

    # If repeat is enabled and in the repeat channel
    if repeat_enabled and repeat_channel_id == message.channel.id:
        if last_record:
            await message.channel.send(last_record)

    await bot.process_commands(message)

# === Run the bot ===
bot.run(TOKEN)

