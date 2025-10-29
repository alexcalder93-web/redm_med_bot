"""
RedM Medical Roster Discord Bot - Render Ready
Google Sheet: WFRP Medical Roster
Chief Role: Chief Doctor
Bot token via environment variable DISCORD_BOT_TOKEN
"""
import os
import discord
from discord import app_commands
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
import pytz
from discord.ext import tasks
import json


# ---------- Config ----------
SHEET_ID = os.environ.get("SHEET_ID", "YOUR_SHEET_ID_HERE")
CREDS_FILE = "credentials.json"
CHIEF_ROLE_NAME = os.environ.get("CHIEF_ROLE_NAME", "Chief Doctor")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
REMINDER_CHANNEL_ID = load_reminder_config()
REMINDER_DAY = 6  # 0=Monday, 6=Sunday
REMINDER_HOUR = 18  # 24-hour format (18 = 6 PM)

ACTIVITY_CHOICES = {
    "Active": "🟢 Active",
    "Semi-Active": "🟡 Semi-Active",
    "Inactive": "⚪ Inactive",
    "LOA": "🟠 LOA",
    "ROA": "🔵 ROA",
    "Suspended": "🔴 Suspended"
}
activity_choices = [discord.app_commands.Choice(name=v, value=k) for k, v in ACTIVITY_CHOICES.items()]

RANK_ORDER = {
    "Chief Doctor": 0,
    "Head Doctor": 1,
    "Senior Doctor": 2,
    "Doctor": 3,
    "Junior Doctor": 4,
    "Apprentice": 5
}

# ---------- Google Sheets Setup ----------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

# ---------- Discord Setup ----------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- Helpers ----------
def is_chief(interaction: discord.Interaction):
    roles = getattr(interaction.user, "roles", []) or []
    return any(getattr(r,"name",None)==CHIEF_ROLE_NAME for r in roles)

async def deny_permission(interaction: discord.Interaction):
    await interaction.response.send_message("🚫 You don't have permission. Chief Doctor only.", ephemeral=True)

def find_row_by_name(name: str):
    data = sheet.get_all_values()
    for i, row in enumerate(data, start=1):
        if len(row)>=1 and row[0].strip().lower()==name.strip().lower():
            return i, row
    return None, None

CONFIG_FILE = "reminder_config.json"

def load_reminder_config():
    """Load reminder channel ID from file."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                data = json.load(f)
                return data.get("reminder_channel_id")
            except json.JSONDecodeError:
                return None
    return None

def save_reminder_config(channel_id: int):
    """Save reminder channel ID to file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"reminder_channel_id": channel_id}, f)


# ---------- Commands ----------
@tree.command(name="adddoctor", description="Add a doctor")
@app_commands.describe(name="Name", rank="Rank", activity="Activity")
@app_commands.choices(activity=activity_choices)
async def adddoctor(interaction: discord.Interaction, name: str, rank: str, activity: app_commands.Choice[str]):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return
    sheet.append_row([name, rank, activity.value, ""])  # Keep Last Promoted blank initially
    await interaction.response.send_message(f"✅ Added {name} as {rank} ({activity.value})")

@tree.command(name="updateactivity", description="Update activity")
@app_commands.describe(name="Name", activity="New activity")
@app_commands.choices(activity=activity_choices)
async def updateactivity(interaction: discord.Interaction, name: str, activity: app_commands.Choice[str]):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return
    row_idx, row = find_row_by_name(name)
    if not row_idx:
        await interaction.response.send_message("❌ Doctor not found")
        return
    sheet.update_cell(row_idx, 3, activity.value)
    await interaction.response.send_message(f"🩺 Updated {name}'s activity to {activity.value}")

@tree.command(name="updaterank", description="Update rank")
@app_commands.describe(name="Name", rank="New rank")
async def updaterank(interaction: discord.Interaction, name: str, rank: str):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return

    row_idx, row = find_row_by_name(name)
    if not row_idx:
        await interaction.response.send_message("❌ Doctor not found")
        return

    # Update rank
    sheet.update_cell(row_idx, 2, rank)
    
    # Update last promoted timestamp (UK time)
    uk_tz = pytz.timezone("Europe/London")
    timestamp = datetime.now(uk_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    sheet.update_cell(row_idx, 4, timestamp)

    await interaction.response.send_message(f"📋 Updated {name}'s rank to {rank} (Last Promoted: {timestamp})")

@tree.command(name="removedoctor", description="Remove doctor")
@app_commands.describe(name="Name")
async def removedoctor(interaction: discord.Interaction, name: str):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return

    # Defer so Discord doesn't time out while calling Google Sheets
    await interaction.response.defer(ephemeral=True)

    try:
        row_idx, row = find_row_by_name(name)
        if not row_idx:
            await interaction.followup.send("❌ Doctor not found")
            return

        # gspread uses delete_rows (plural). This deletes a single row.
        sheet.delete_rows(row_idx)

        await interaction.followup.send(f"🗑️ Removed {name}")
    except Exception as e:
        # Provide the error so you can debug quickly
        await interaction.followup.send(f"⚠️ Error removing doctor: `{e}`")

@tree.command(name="showroster", description="Show roster")
async def showroster(interaction: discord.Interaction):
    data = sheet.get_all_values()
    if len(data) <= 1:
        await interaction.response.send_message("📋 Roster empty")
        return

    # Prepare roster rows
    roster_rows = [
        {
            "name": row[0],
            "rank": row[1],
            "activity": ACTIVITY_CHOICES.get(row[2], row[2]),
            "last_promoted": row[3] if len(row) >= 4 else "N/A"
        }
        for row in data[1:] if len(row) >= 3
    ]

    # Sort by rank using RANK_ORDER
    roster_rows.sort(key=lambda x: RANK_ORDER.get(x["rank"], 99))

    # Build display lines
    roster_lines = [
        f"**{r['name']}** | **RANK:** {r['rank']} | **ACTIVITY:** {r['activity']} | **LAST PROMOTED:** {r['last_promoted']}"
        for r in roster_rows
    ]

    chunk = "\n".join(roster_lines)[:3900]

    embed = discord.Embed(
        title="🏥 WFRP Medical Roster",
        description=chunk,
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)

@tree.command(name="setreminderchannel", description="Set the weekly reminder channel")
async def setreminderchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return

    global REMINDER_CHANNEL_ID
    REMINDER_CHANNEL_ID = channel.id
    save_reminder_config(channel.id)

    await interaction.response.send_message(f"✅ Weekly reminder channel set to {channel.mention}")

@tasks.loop(minutes=60)
async def weekly_reminder():
    """Runs hourly and checks if it's the scheduled reminder time (Sunday 18:00 UK)."""
    uk_tz = pytz.timezone("Europe/London")
    now = datetime.now(uk_tz)

    if now.weekday() == REMINDER_DAY and now.hour == REMINDER_HOUR:
        channel_id = REMINDER_CHANNEL_ID or load_reminder_config()
channel = client.get_channel(channel_id) if channel_id else None
        if not channel:
            print("⚠️ Reminder channel not found.")
            return

        data = sheet.get_all_values()
        if len(data) <= 1:
            await channel.send("📋 The medical roster is empty — no reminders to show.")
            return

        # Categorize members by status
        inactive = []
        loa = []
        roa = []
        suspended = []

        for row in data[1:]:
            if len(row) < 3:
                continue
            name, rank, status = row[0], row[1], row[2]
            if status == "Inactive":
                inactive.append(f"• {name} ({rank})")
            elif status == "LOA":
                loa.append(f"• {name} ({rank})")
            elif status == "ROA":
                roa.append(f"• {name} ({rank})")
            elif status == "Suspended":
                suspended.append(f"• {name} ({rank})")

        embed = discord.Embed(
            title="🩺 Weekly Medical Roster Reminder",
            color=discord.Color.red(),
            timestamp=now
        )

        if inactive:
            embed.add_field(name="⚪ Inactive", value="\n".join(inactive), inline=False)
        if loa:
            embed.add_field(name="🟠 LOA", value="\n".join(loa), inline=False)
        if roa:
            embed.add_field(name="🔵 ROA", value="\n".join(roa), inline=False)
        if suspended:
            embed.add_field(name="🔴 Suspended", value="\n".join(suspended), inline=False)

        if not any([inactive, loa, roa, suspended]):
            embed.description = "✅ Everyone is active this week!"

        await channel.send(embed=embed)


@client.event
async def on_ready():
    await tree.sync()
    if not weekly_reminder.is_running():
        weekly_reminder.start()
    print(f"✅ Logged in as {client.user}")

