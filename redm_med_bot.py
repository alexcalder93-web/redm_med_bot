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


# ---------- Config ----------
SHEET_ID = os.environ.get("SHEET_ID", "YOUR_SHEET_ID_HERE")
CREDS_FILE = "credentials.json"
CHIEF_ROLE_NAME = os.environ.get("CHIEF_ROLE_NAME", "Chief Doctor")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

ACTIVITY_OPTIONS = ["Active","Semi-Active","Inactive","LOA","ROA","Suspended"]

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

# ---------- Commands ----------
@tree.command(name="adddoctor", description="Add a doctor")
@app_commands.describe(name="Name", rank="Rank", activity="Activity")
@app_commands.choices(activity=[app_commands.Choice(name=a,value=a) for a in ACTIVITY_OPTIONS])
async def adddoctor(interaction: discord.Interaction, name: str, rank: str, activity: app_commands.Choice[str]):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return
    sheet.append_row([name, rank, activity.value])
    await interaction.response.send_message(f"✅ Added {name} as {rank} ({activity.value})")

@tree.command(name="updateactivity", description="Update activity")
@app_commands.describe(name="Name", activity="New activity")
@app_commands.choices(activity=[app_commands.Choice(name=a,value=a) for a in ACTIVITY_OPTIONS])
async def updateactivity(interaction: discord.Interaction, name: str, activity: app_commands.Choice[str]):
    if not is_chief(interaction):
        await deny_permission(interaction)
        return
    row_idx,row=find_row_by_name(name)
    if not row_idx:
        await interaction.response.send_message("❌ Doctor not found")
        return
    sheet.update_cell(row_idx,3,activity.value)
    await interaction.response.send_message(f"🩺 Updated {name} activity to {activity.value}")

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
    row_idx,row=find_row_by_name(name)
    if not row_idx:
        await interaction.response.send_message("❌ Doctor not found")
        return
    sheet.delete_row(row_idx)
    await interaction.response.send_message(f"🗑️ Removed {name}")

@tree.command(name="showroster", description="Show roster")
async def showroster(interaction: discord.Interaction):
    data=sheet.get_all_values()
    if len(data)<=1:
        await interaction.response.send_message("📋 Roster empty")
        return
roster_lines = [
    f"**{row[0]}** — {row[1]} ({row[2]}) | Last Promoted: {row[3] if len(row)>=4 else 'N/A'}"
    for row in data[1:] if len(row)>=3]
    embed=discord.Embed(title="🏥 WFRP Medical Roster", description=chunk, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")
client.run(BOT_TOKEN)
