import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1543281300192895097
BIRTHDAY_CHANNEL = "🤌〢yappy-yapˎˊ˗"

# Existing birthdays without a timezone will use IST.
DEFAULT_TIMEZONE = "Asia/Kolkata"


# ============================================================
# TIMEZONE ALIASES
# ============================================================
#
# Members can use simple timezone codes instead of typing
# long IANA timezone names.
#
# Examples:
# IST -> India
# SGT -> Singapore
# GMT -> GMT
# ET  -> US Eastern Time
# PT  -> US Pacific Time
#
# More specific IANA timezone names can also be entered
# directly, e.g. Europe/London or Asia/Tokyo.
#

TIMEZONE_ALIASES = {
    # Asia
    "IST": "Asia/Kolkata",
    "SGT": "Asia/Singapore",
    "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "CST": "Asia/Shanghai",
    "HKT": "Asia/Hong_Kong",
    "PHT": "Asia/Manila",
    "WIB": "Asia/Jakarta",
    "ICT": "Asia/Bangkok",
    "PKT": "Asia/Karachi",
    "BST": "Asia/Dhaka",
    "NPT": "Asia/Kathmandu",
    "GST": "Asia/Dubai",

    # Europe
    "GMT": "Etc/GMT",
    "WET": "Europe/Lisbon",
    "CET": "Europe/Paris",
    "EET": "Europe/Athens",
    "MSK": "Europe/Moscow",

    # North America
    #
    # ET/CT/MT/PT automatically handle daylight saving time.
    "ET": "America/New_York",
    "CT": "America/Chicago",
    "MT": "America/Denver",
    "PT": "America/Los_Angeles",

    # Fixed US abbreviations
    "EST": "Etc/GMT+5",
    "CST_US": "Etc/GMT+6",
    "MST": "Etc/GMT+7",
    "PST": "Etc/GMT+8",

    # Australia / Pacific
    "AEST": "Australia/Brisbane",
    "ACST": "Australia/Adelaide",
    "AWST": "Australia/Perth",
    "NZST": "Pacific/Auckland",

    # Africa
    "CAT": "Africa/Harare",
    "EAT": "Africa/Nairobi",
    "SAST": "Africa/Johannesburg",
    "WAT": "Africa/Lagos",
}


def resolve_timezone(timezone_input: str):
    """
    Convert a friendly timezone abbreviation or an IANA
    timezone name into a valid IANA timezone.
    """

    cleaned = timezone_input.strip()

    # Try friendly abbreviation first.
    alias = TIMEZONE_ALIASES.get(cleaned.upper())

    if alias:
        return alias

    # Otherwise try the input directly as an IANA timezone.
    try:
        ZoneInfo(cleaned)
        return cleaned
    except ZoneInfoNotFoundError:
        return None


# ============================================================
# DATABASE
# ============================================================

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


# ------------------------------------------------------------
# DATABASE MIGRATION
# ------------------------------------------------------------
#
# Add timezone + last wished year to existing databases.
#
# Existing birthdays are automatically treated as IST.
#

columns = {
    row["name"]
    for row in db.execute(
        "PRAGMA table_info(birthdays)"
    ).fetchall()
}

if "timezone" not in columns:
    db.execute(
        """
        ALTER TABLE birthdays
        ADD COLUMN timezone TEXT NOT NULL
        DEFAULT 'Asia/Kolkata'
        """
    )

if "last_wished_year" not in columns:
    db.execute(
        """
        ALTER TABLE birthdays
        ADD COLUMN last_wished_year INTEGER
        """
    )

db.commit()


# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# ============================================================
# BIRTHDAY COMMAND GROUP
# ============================================================

birthday_group = app_commands.Group(
    name="birthday",
    description="Manage birthdays"
)


# ============================================================
# /birthday set
# ============================================================

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

    # --------------------------------------------------------
    # CHECK DATE FORMAT
    # --------------------------------------------------------

    try:
        day, month = map(int, date.split("/"))
    except (ValueError, AttributeError):
        return await interaction.response.send_message(
            "❌ Please use **DD/MM** format.\n"
            "Example: `15/04`",
            ephemeral=True,
        )

    # --------------------------------------------------------
    # CHECK VALID DATE
    # --------------------------------------------------------

    try:
        datetime(2000, month, day)
    except ValueError:
        return await interaction.response.send_message(
            "❌ That's not a valid date.",
            ephemeral=True,
        )

    # --------------------------------------------------------
    # CHECK TIMEZONE
    # --------------------------------------------------------

    resolved_timezone = resolve_timezone(timezone)

    if resolved_timezone is None:
        return await interaction.response.send_message(
            "❌ I don't recognize that timezone.\n\n"
            "**Examples:** `IST`, `SGT`, `GMT`, `ET`, "
            "`CT`, `MT`, `PT`, `JST`, `CET`\n\n"
            "You can also use an IANA timezone such as "
            "`Asia/Tokyo` or `Europe/London`.",
            ephemeral=True,
        )

    # --------------------------------------------------------
    # SAVE / UPDATE BIRTHDAY
    # --------------------------------------------------------

    db.execute(
        """
        INSERT INTO birthdays (
            user_id,
            birthday_day,
            birthday_month,
            timezone,
            last_wished_year
        )
        VALUES (?, ?, ?, ?, NULL)

        ON CONFLICT(user_id)
        DO UPDATE SET
            birthday_day = excluded.birthday_day,
            birthday_month = excluded.birthday_month,
            timezone = excluded.timezone
        """,
        (
            str(member.id),
            day,
            month,
            resolved_timezone,
        ),
    )

    db.commit()

    # --------------------------------------------------------
    # PRIVATE CONFIRMATION
    # --------------------------------------------------------

    await interaction.response.send_message(
        f"🎂 Birthday saved for {member.mention}!\n\n"
        f"📅 **Date:** {day:02d}/{month:02d}\n"
        f"🌍 **Timezone:** `{timezone.upper()}`\n"
        f"🕐 **Using:** `{resolved_timezone}`\n\n"
        f"🎉 I'll wish them at **12:00 AM in their timezone**.",
        ephemeral=True,
    )

    print(
        f"BIRTHDAY SET: "
        f"{member} ({member.id}) → "
        f"{day:02d}/{month:02d} → "
        f"{resolved_timezone}"
    )


# ============================================================
# ADD COMMAND GROUP
# ============================================================

bot.tree.add_command(
    birthday_group,
    guild=discord.Object(id=GUILD_ID),
)


# ============================================================
# DAILY BIRTHDAY CHECK
# ============================================================

@tasks.loop(minutes=1)
async def birthday_checker():

    rows = db.execute(
        """
        SELECT
            user_id,
            birthday_day,
            birthday_month,
            timezone,
            last_wished_year
        FROM birthdays
        """
    ).fetchall()

    if not rows:
        return

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return

    channel = discord.utils.get(
        guild.text_channels,
        name=BIRTHDAY_CHANNEL,
    )

    if channel is None:
        print(
            f"ERROR: Birthday channel "
            f"#{BIRTHDAY_CHANNEL} not found."
        )
        return

    # --------------------------------------------------------
    # CHECK EACH MEMBER IN THEIR OWN TIMEZONE
    # --------------------------------------------------------

    for row in rows:

        user_id = int(row["user_id"])

        timezone_name = row["timezone"] or DEFAULT_TIMEZONE

        try:
            member_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            print(
                f"INVALID TIMEZONE for member {user_id}: "
                f"{timezone_name}"
            )
            continue

        now = datetime.now(member_timezone)

        # ----------------------------------------------------
        # Only continue at midnight in THIS member's timezone.
        # ----------------------------------------------------

        if now.hour != 0 or now.minute != 0:
            continue

        # ----------------------------------------------------
        # Check birthday date.
        # ----------------------------------------------------

        if (
            now.day != row["birthday_day"]
            or now.month != row["birthday_month"]
        ):
            continue

        # ----------------------------------------------------
        # Prevent duplicate birthday wishes.
        # ----------------------------------------------------

        if row["last_wished_year"] == now.year:
            continue

        # ----------------------------------------------------
        # Get member.
        # ----------------------------------------------------

        member = guild.get_member(user_id)

        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                print(
                    f"BIRTHDAY SKIPPED: "
                    f"member {user_id} not found."
                )
                continue
            except discord.HTTPException as e:
                print(
                    f"BIRTHDAY MEMBER ERROR: {e}"
                )
                continue

        # ----------------------------------------------------
        # Send birthday message.
        # ----------------------------------------------------

        await channel.send(
            f"🎂🫧 **HAPPY BIRTHDAY, {member.mention}!** 🫧🎂\n\n"
            f"Hope you have the most amazing birthday! 💗\n"
            f"Have a wonderful day! 🎉✨"
        )

        # ----------------------------------------------------
        # Record that this year's wish was sent.
        # ----------------------------------------------------

        db.execute(
            """
            UPDATE birthdays
            SET last_wished_year = ?
            WHERE user_id = ?
            """,
            (
                now.year,
                str(user_id),
            ),
        )

        db.commit()

        print(
            f"BIRTHDAY WISH SENT: "
            f"{member} ({member.id}) → "
            f"{timezone_name} → "
            f"{now.year}"
        )


@birthday_checker.before_loop
async def before_birthday_checker():
    await bot.wait_until_ready()


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    # Clear old global commands so stale commands
    # don't remain registered.
    bot.tree.clear_commands(guild=None)

    await bot.tree.sync()

    # Sync only this server's birthday command.
    synced = await bot.tree.sync(
        guild=discord.Object(id=GUILD_ID)
    )

    if not birthday_checker.is_running():
        birthday_checker.start()

    print(f"Logged in as {bot.user}")
    print(
        f"Synced {len(synced)} commands "
        f"to server {GUILD_ID}"
    )
    print("Birthday system is ready.")


# ============================================================
# START
# ============================================================

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from Railway Variables."
    )

bot.run(TOKEN)
