import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1543281300192895097
BIRTHDAY_CHANNEL = "🤌〢yappy-yapˎˊ˗"
DEFAULT_TIMEZONE = "Asia/Kolkata"

TIMEZONE_ALIASES = {
    "IST": "Asia/Kolkata", "SGT": "Asia/Singapore", "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul", "CST": "Asia/Shanghai", "HKT": "Asia/Hong_Kong",
    "PHT": "Asia/Manila", "WIB": "Asia/Jakarta", "ICT": "Asia/Bangkok",
    "PKT": "Asia/Karachi", "BST": "Asia/Dhaka", "NPT": "Asia/Kathmandu",
    "GST": "Asia/Dubai", "GMT": "Etc/GMT", "WET": "Europe/Lisbon",
    "CET": "Europe/Paris", "EET": "Europe/Athens", "MSK": "Europe/Moscow",
    "ET": "America/New_York", "CT": "America/Chicago", "MT": "America/Denver",
    "PT": "America/Los_Angeles", "EST": "Etc/GMT+5", "CST_US": "Etc/GMT+6",
    "MST": "Etc/GMT+7", "PST": "Etc/GMT+8", "AEST": "Australia/Brisbane",
    "ACST": "Australia/Adelaide", "AWST": "Australia/Perth", "NZST": "Pacific/Auckland",
    "CAT": "Africa/Harare", "EAT": "Africa/Nairobi", "SAST": "Africa/Johannesburg",
    "WAT": "Africa/Lagos",
}


def resolve_timezone(timezone_input: str):
    cleaned = timezone_input.strip()
    alias = TIMEZONE_ALIASES.get(cleaned.upper())
    if alias:
        return alias
    try:
        ZoneInfo(cleaned)
        return cleaned
    except ZoneInfoNotFoundError:
        return None


DB_FILE = "birthdays.db"
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row

db.execute("""
CREATE TABLE IF NOT EXISTS birthdays (
    user_id TEXT PRIMARY KEY,
    birthday_day INTEGER NOT NULL,
    birthday_month INTEGER NOT NULL
)
""")
db.commit()

columns = {row["name"] for row in db.execute("PRAGMA table_info(birthdays)").fetchall()}

if "timezone" not in columns:
    db.execute("""
        ALTER TABLE birthdays ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata'
    """)

if "last_wished_year" not in columns:
    db.execute("""
        ALTER TABLE birthdays ADD COLUMN last_wished_year INTEGER
    """)

db.commit()


# Message Content Intent is enabled here as well as in the Developer Portal.
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

birthday_group = app_commands.Group(
    name="birthday",
    description="Manage birthdays"
)


@birthday_group.command(
    name="set",
    description="Set a member's birthday and timezone",
)
@app_commands.describe(
    member="The member whose birthday you are setting",
    date="Birthday in DD/MM format",
    timezone="Timezone, e.g. IST, SGT, GMT, ET, PT, or Asia/Tokyo",
)
async def birthday_set(
    interaction: discord.Interaction,
    member: discord.Member,
    date: str,
    timezone: str,
):
    try:
        day, month = map(int, date.split("/"))
    except (ValueError, AttributeError):
        return await interaction.response.send_message(
            "❌ Please use **DD/MM** format.\nExample: `15/04`",
            ephemeral=True,
        )

    try:
        datetime(2000, month, day)
    except ValueError:
        return await interaction.response.send_message(
            "❌ That's not a valid date.", ephemeral=True
        )

    resolved_timezone = resolve_timezone(timezone)
    if resolved_timezone is None:
        return await interaction.response.send_message(
            "❌ I don't recognize that timezone.\n\n"
            "**Examples:** `IST`, `SGT`, `GMT`, `ET`, `CT`, `MT`, `PT`, `JST`, `CET`\n\n"
            "You can also use an IANA timezone such as `Asia/Tokyo` or `Europe/London`.",
            ephemeral=True,
        )

    db.execute("""
        INSERT INTO birthdays (
            user_id, birthday_day, birthday_month, timezone, last_wished_year
        )
        VALUES (?, ?, ?, ?, NULL)
        ON CONFLICT(user_id) DO UPDATE SET
            birthday_day = excluded.birthday_day,
            birthday_month = excluded.birthday_month,
            timezone = excluded.timezone
    """, (str(member.id), day, month, resolved_timezone))
    db.commit()

    await interaction.response.send_message(
        f"🎂 Birthday saved for {member.mention}!\n\n"
        f"📅 **Date:** {day:02d}/{month:02d}\n"
        f"🌍 **Timezone:** `{timezone.upper()}`\n"
        f"🕐 **Using:** `{resolved_timezone}`\n\n"
        f"🎉 I'll wish them at **12:00 AM in their timezone**.",
        ephemeral=True,
    )

    print(
        f"BIRTHDAY SET: {member} ({member.id}) → "
        f"{day:02d}/{month:02d} → {resolved_timezone}"
    )


bot.tree.add_command(birthday_group, guild=discord.Object(id=GUILD_ID))


@tasks.loop(minutes=1)
async def birthday_checker():
    rows = db.execute("""
        SELECT user_id, birthday_day, birthday_month, timezone, last_wished_year
        FROM birthdays
    """).fetchall()

    if not rows:
        return

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("ERROR: Birthday guild not found.")
        return

    channel = discord.utils.get(guild.text_channels, name=BIRTHDAY_CHANNEL)
    if channel is None:
        print(f"ERROR: Birthday channel #{BIRTHDAY_CHANNEL} not found.")
        return

    for row in rows:
        user_id = int(row["user_id"])
        timezone_name = row["timezone"] or DEFAULT_TIMEZONE

        try:
            member_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            print(f"INVALID TIMEZONE for member {user_id}: {timezone_name}")
            continue

        now = datetime.now(member_timezone)

        # Do not require the checker to hit exactly 00:00.
        # If Railway is delayed/restarted, the birthday is still sent later that day.
        if now.day != row["birthday_day"] or now.month != row["birthday_month"]:
            continue

        if row["last_wished_year"] == now.year:
            continue

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                print(f"BIRTHDAY SKIPPED: member {user_id} not found.")
                continue
            except discord.HTTPException as e:
                print(f"BIRTHDAY MEMBER ERROR: {e}")
                continue

        try:
            await channel.send(
                f"🎂🫧 **HAPPY BIRTHDAY, {member.mention}!** 🫧🎂\n\n"
                f"Hope you have the most amazing birthday! 💗\n"
                f"Have a wonderful day! 🎉✨"
            )

            db.execute("""
                UPDATE birthdays
                SET last_wished_year = ?
                WHERE user_id = ?
            """, (now.year, str(user_id)))
            db.commit()

            print(
                f"BIRTHDAY WISH SENT: {member} ({member.id}) → "
                f"{timezone_name} → {now.year}"
            )

        except discord.HTTPException as e:
            print(f"BIRTHDAY SEND ERROR for {member} ({member.id}): {e}")


@birthday_checker.before_loop
async def before_birthday_checker():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()

    synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    if not birthday_checker.is_running():
        birthday_checker.start()
        print("Birthday checker started.")

    print(f"Logged in as {bot.user}")
    print(f"Synced {len(synced)} commands to server {GUILD_ID}")
    print("Birthday system is ready.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from Railway Variables.")

bot.run(TOKEN)
