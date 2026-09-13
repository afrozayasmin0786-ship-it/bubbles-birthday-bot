import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1543281300192895097
BIRTHDAY_CHANNEL = "🤌〢yappy-yapˎˊ˗"

TIMEZONE = ZoneInfo("Asia/Kolkata")


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


@birthday_group.command(
    name="set",
    description="Set a member's birthday",
)
@app_commands.describe(
    member="The member whose birthday you are setting",
    date="Birthday in DD/MM format",
)
async def birthday_set(
    interaction: discord.Interaction,
    member: discord.Member,
    date: str,
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
    # SAVE / UPDATE BIRTHDAY
    # --------------------------------------------------------

    db.execute(
        """
        INSERT INTO birthdays (
            user_id,
            birthday_day,
            birthday_month
        )
        VALUES (?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            birthday_day = excluded.birthday_day,
            birthday_month = excluded.birthday_month
        """,
        (
            str(member.id),
            day,
            month,
        ),
    )

    db.commit()

    # --------------------------------------------------------
    # PRIVATE CONFIRMATION
    # --------------------------------------------------------

    await interaction.response.send_message(
        f"🎂 Birthday saved for {member.mention} — "
        f"**{day:02d}/{month:02d}**!",
        ephemeral=True,
    )

    print(
        f"BIRTHDAY SET: "
        f"{member} ({member.id}) → {day:02d}/{month:02d}"
    )


# Add the group to the bot's command tree.
bot.tree.add_command(
    birthday_group,
    guild=discord.Object(id=GUILD_ID),
)


# ============================================================
# DAILY BIRTHDAY CHECK
# ============================================================

@tasks.loop(minutes=1)
async def birthday_checker():

    now = datetime.now(TIMEZONE)

    # Only run the birthday check at exactly midnight.
    if now.hour != 0 or now.minute != 0:
        return

    rows = db.execute(
        """
        SELECT user_id
        FROM birthdays
        WHERE birthday_day = ?
        AND birthday_month = ?
        """,
        (
            now.day,
            now.month,
        ),
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

    for row in rows:

        user_id = int(row["user_id"])

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

        await channel.send(
            f"🎂🫧 **HAPPY BIRTHDAY, {member.mention}!** 🫧🎂\n\n"
            f"Hope you have the most amazing birthday! 💗\n"
            f"Have a wonderful day! 🎉✨"
        )

        print(
            f"BIRTHDAY WISH SENT: "
            f"{member} ({member.id})"
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