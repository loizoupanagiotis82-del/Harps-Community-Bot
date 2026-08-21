import asyncio
import io
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks


TOKEN = os.getenv("DISCORD_TOKEN")

STAFF_ROLE_NAMES = [
    "Founder",
    "Owner",
    "Co Owner",
    "Administrator",
    "Moderator",
]

TICKET_CATEGORY_NAME = "🎫 TICKETS"
TICKET_LOG_CATEGORY_NAME = "📁 TICKET LOGS"
SERVER_STATS_CATEGORY_NAME = "📊 SERVER STATS"
MEMBER_COUNT_CHANNEL_PREFIX = "👥 Members:"
WELCOME_CHANNEL_NAME = "📜・welcome"
GOODBYE_CHANNEL_NAME = "📜・goodbye"
RULES_CHANNEL_NAME = "📚server-rules"
MOD_LOG_CATEGORY_NAME = "🛡️ MODERATION LOGS"
AUTO_ROLE_NAME = "🔥│Regulars"
ROLE_REQUEST_PANEL_CHANNEL_NAME = "🕴role-request"
ROLE_REQUEST_CATEGORY_NAME = "🎭 ROLE REQUESTS"
BOOST_PANEL_CHANNEL_NAME = "🚀server-boost"
SERVER_LOG_CATEGORY_NAME = "📋 SERVER LOGS"
ANTINUKE_WHITELIST_ROLE_NAME = "🛡️ Anti-Nuke Whitelist"
ANTINUKE_MASS_THRESHOLD = 3
ANTINUKE_WINDOW_SECONDS = 10
SAFETY_CATEGORY_NAME = "🛡️ SAFETY CENTER"
SAFETY_REVIEW_CHANNEL_NAME = "safety-review"
SAFETY_LOG_CHANNEL_NAME = "safety-logs"
SAFETY_WHITELIST_ROLE_NAME = "🛡️ Safety Whitelist"
SAFETY_SPAM_WINDOW_SECONDS = 5
SAFETY_DUPLICATE_WINDOW_SECONDS = 15
SAFETY_INCIDENT_COOLDOWN_SECONDS = 30
SAFETY_BAN_DELETE_SECONDS = 7 * 24 * 60 * 60

# These defaults control spam and mass-mention review/timeout thresholds.
# Links and @everyone/@here pings use the separate immediate-ban rule below.
SAFETY_DEFAULT_CONFIG = {
    "spam_review": 6,
    "spam_auto": 10,
    "mention_review": 5,
    "mention_auto": 8,
    "duplicate_review": 3,
    "duplicate_auto": 6,
    "timeout_minutes": 10,
}

# Matches normal URLs, Discord invites, www links and bare domains.
LINK_PATTERN = re.compile(
    r"(?:https?://|www\.)[^\s<]+|"
    r"(?<![@\w])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}(?::\d{2,5})?(?:/[^\s<]*)?",
    re.IGNORECASE,
)

# Exact channel names added here are ignored by chat safety checks.
SAFETY_EXEMPT_CHANNEL_NAMES: set[str] = set()

LFG_CATEGORY_NAME = "🎮 LOOKING FOR GROUP"
LFG_RULES_CHANNEL_NAME = "📌・lfg-rules"
LFG_CREATE_CHANNEL_NAME = "🎮・create-lfg"
LFG_ACTIVE_CHANNEL_NAME = "🔎・active-lfg"
LFG_COMPLETED_CHANNEL_NAME = "✅・completed-lfg"
LFG_LOG_CHANNEL_NAME = "lfg-logs"
LFG_VOICE_CREATOR_NAME = "🔊・Create Voice Room"
LFG_TEMP_VOICE_PREFIX = "🎧│"
LFG_EXPIRY_HOURS = 6

LFG_GAMES = {
    "valorant": "VALORANT",
    "cs2": "Counter-Strike 2",
    "cod": "Call of Duty / Warzone",
    "fortnite": "Fortnite",
    "rocket_league": "Rocket League",
    "minecraft": "Minecraft",
    "roblox": "Roblox",
    "apex": "Apex Legends",
    "overwatch_2": "Overwatch 2",
    "rainbow_six": "Rainbow Six Siege",
    "gta_online": "GTA Online",
    "ea_fc": "EA Sports FC",
}

LFG_REGIONS = {
    "eu": "Europe",
    "me": "Middle East",
    "na_east": "North America East",
    "na_west": "North America West",
    "asia": "Asia",
    "oce": "Oceania",
}

LFG_PLATFORMS = {
    "pc": "PC",
    "playstation": "PlayStation",
    "xbox": "Xbox",
    "crossplay": "Crossplay",
}

LFG_TEAM_SIZES = {
    "2": "Duo",
    "3": "Trio",
    "4": "Squad",
    "5": "5 Stack",
    "10": "Custom Team",
}

# IDs placed here are always trusted, including bots that are not in the server yet.
ANTINUKE_WHITELIST_IDS: set[int] = set()

# Leave empty to show every safe, non-staff role (up to Discord's 25-option
# limit), or add exact role names here to control what members may request.
ROLE_REQUEST_ALLOWED_ROLE_NAMES: list[str] = []

SERVER_LOG_CHANNELS = {
    "member": "member-logs",
    "message": "message-logs",
    "reaction": "reaction-logs",
    "voice": "voice-logs",
    "channel": "channel-logs",
    "role": "role-logs",
    "server": "server-logs",
    "antinuke": "anti-nuke-logs",
}

MOD_LOG_CHANNELS = {
    "kick": "kick-logs",
    "ban": "ban-logs",
    "clear": "cleared-logs",
    "server": "server-logs",
}

SERVER_RULES = """• Απαγορεύονται οι προσωπικές επιθέσεις, ο σεξισμός, ο ρατσισμός και οτιδήποτε σχετικό και οποιαδήποτε υποστήριξη των παραπάνω.

• Δεν επιτρέπεται το ακατάλληλο περιεχόμενο 

• Δεν επιτρέπονται οι διαφημίσεις 

• Απαγορεύεται να κάνετε tag τα μέλη του server ή οποιοδήποτε μέλος του προσωπικού, εκτός εάν έχετε κάποια ερώτηση.

• Δεν επιτρέπεται το spam

• Μην διαφημίζετε discord server, social media, websites ή οτιδήποτε άλλο στον server μας και στα προσωπικά μηνύματα των member.

• Απαγορεύεται η χρήση των alts για να αποκτήσετε πλεονεκτήματα στον server μας. Απαγορεύετε η χρήση των self-bot.

• Απαγορεύεται το NSFW και το ακατάλληλο περιεχόμενο.

• Βεβαιωθείτε ότι έχετε δημοσιεύσει το περιεχόμενό σας στο πιο κατάλληλο κανάλι. Σε περίπτωση που γράψετε σε άλλο κανάλι θα διαγράφεται το μήνυμα σας.

Ακολουθήστε τους [Όρους Παροχής Υπηρεσιών του Discord](https://discord.com/terms) και τις [Οδηγίες κοινότητας](https://discord.com/guidelines)."""

TICKET_TYPES = {
    "general": ("General Support", "general-support-logs"),
    "report": ("Report a Member", "member-report-logs"),
    "partnership": ("Partnership / Other", "partnership-other-logs"),
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
ticket_creation_locks: dict[tuple[int, int, str], asyncio.Lock] = {}
role_request_locks: dict[tuple[int, int], asyncio.Lock] = {}
role_decision_locks: dict[int, asyncio.Lock] = {}
antinuke_activity: dict[tuple[int, int, str], deque[float]] = defaultdict(deque)
antinuke_triggered: set[tuple[int, int]] = set()
server_log_setup_locks: dict[int, asyncio.Lock] = {}
recent_member_removals: dict[int, deque[tuple[float, int]]] = defaultdict(deque)
last_member_removal_check: dict[int, float] = {}
safety_message_activity: dict[tuple[int, int], deque[float]] = defaultdict(deque)
safety_duplicate_activity: dict[
    tuple[int, int], deque[tuple[float, str]]
] = defaultdict(deque)
safety_incident_cooldowns: dict[tuple[int, int, str], float] = {}
safety_setup_locks: dict[int, asyncio.Lock] = {}
safety_review_action_locks: dict[int, asyncio.Lock] = {}
lfg_setup_locks: dict[int, asyncio.Lock] = {}
lfg_creation_locks: dict[tuple[int, int], asyncio.Lock] = {}
lfg_listing_locks: dict[int, asyncio.Lock] = {}
lfg_voice_locks: dict[tuple[int, int], asyncio.Lock] = {}
lfg_temp_voice_owners: dict[int, int] = {}
slash_commands_synced = False


def is_staff(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(
        role.name in STAFF_ROLE_NAMES for role in member.roles
    )


def ticket_topic(user_id: int, ticket_type: str) -> str:
    return f"harps-ticket:user={user_id};type={ticket_type}"


def ticket_creator_id(channel: discord.TextChannel) -> int | None:
    match = re.search(r"harps-ticket:user=(\d+);", channel.topic or "")
    return int(match.group(1)) if match else None


def ticket_type_from_channel(channel: discord.TextChannel) -> str | None:
    match = re.search(r";type=([a-z-]+)", channel.topic or "")
    return match.group(1) if match else None


def staff_overwrites(guild: discord.Guild) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        )
    for role in guild.roles:
        if role.name in STAFF_ROLE_NAMES:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )
    return overwrites


def shortened(value: object, limit: int = 1000) -> str:
    text = str(value) if value not in (None, "") else "[none]"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def server_banner_url(guild: discord.Guild) -> str | None:
    """Return the best full-width server artwork Discord makes available."""
    artwork = guild.banner or guild.splash or guild.discovery_splash
    return artwork.with_size(1024).url if artwork is not None else None


async def get_server_log_channel(
    guild: discord.Guild, log_type: str, *, create_if_missing: bool = True
) -> discord.TextChannel | None:
    channel_name = SERVER_LOG_CHANNELS.get(log_type, SERVER_LOG_CHANNELS["server"])
    category = discord.utils.get(guild.categories, name=SERVER_LOG_CATEGORY_NAME)
    if category is not None:
        existing = discord.utils.get(category.text_channels, name=channel_name)
        if existing is not None or not create_if_missing:
            return existing
    elif not create_if_missing:
        return None

    lock = server_log_setup_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        category = discord.utils.get(guild.categories, name=SERVER_LOG_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(
                SERVER_LOG_CATEGORY_NAME,
                overwrites=staff_overwrites(guild),
                reason="Harps Community server logging setup",
            )
        channel = discord.utils.get(category.text_channels, name=channel_name)
        if channel is None:
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=staff_overwrites(guild),
                topic=f"Harps Community {channel_name.replace('-', ' ')}",
                reason="Harps Community server logging setup",
            )
        return channel


async def ensure_server_logging(guild: discord.Guild) -> list[discord.TextChannel]:
    channels = []
    for log_type in SERVER_LOG_CHANNELS:
        channel = await get_server_log_channel(guild, log_type)
        if channel is not None:
            channels.append(channel)
    return channels


async def send_server_log(
    guild: discord.Guild,
    log_type: str,
    title: str,
    description: str,
    *,
    color: discord.Color = discord.Color.blurple(),
    fields: list[tuple[str, str, bool]] | None = None,
) -> bool:
    try:
        channel = await get_server_log_channel(guild, log_type)
        if channel is None:
            return False
        embed = discord.Embed(
            title=title,
            description=shortened(description, 4000),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        for name, value, inline in fields or []:
            embed.add_field(
                name=shortened(name, 250), value=shortened(value, 1024), inline=inline
            )
        embed.set_footer(text="Harps Community • Server Audit Log")
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not save {log_type} log in {guild.name}: {error}")
        return False


def safety_config_topic(config: dict[str, int]) -> str:
    values = ";".join(f"{key}={config[key]}" for key in SAFETY_DEFAULT_CONFIG)
    return f"Harps Community staff review queue | harps-safety:v1;{values}"


def safety_config_from_channel(
    channel: discord.TextChannel | None,
) -> dict[str, int]:
    config = SAFETY_DEFAULT_CONFIG.copy()
    if channel is None or "harps-safety:v1;" not in (channel.topic or ""):
        return config
    for key, value in re.findall(r"([a-z_]+)=(\d+)", channel.topic or ""):
        if key in config:
            config[key] = int(value)
    return config


def is_safety_whitelisted(member: discord.Member) -> bool:
    return (
        member.bot
        or member.guild.owner_id == member.id
        or is_staff(member)
        or any(
            role.name in {SAFETY_WHITELIST_ROLE_NAME, ANTINUKE_WHITELIST_ROLE_NAME}
            for role in member.roles
        )
    )


def is_safety_exempt_channel(channel: discord.abc.GuildChannel) -> bool:
    if channel.name in SAFETY_EXEMPT_CHANNEL_NAMES:
        return True
    category = getattr(channel, "category", None)
    return category is not None and category.name in {
        SAFETY_CATEGORY_NAME,
        SERVER_LOG_CATEGORY_NAME,
        MOD_LOG_CATEGORY_NAME,
        TICKET_LOG_CATEGORY_NAME,
    }


async def ensure_safety_whitelist_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=SAFETY_WHITELIST_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=SAFETY_WHITELIST_ROLE_NAME,
            permissions=discord.Permissions.none(),
            reason="Harps Community chat safety setup",
        )
    return role


async def ensure_safety_center(
    guild: discord.Guild,
) -> tuple[discord.CategoryChannel, discord.TextChannel, discord.TextChannel, discord.Role]:
    lock = safety_setup_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        role = await ensure_safety_whitelist_role(guild)
        category = discord.utils.get(guild.categories, name=SAFETY_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(
                SAFETY_CATEGORY_NAME,
                overwrites=staff_overwrites(guild),
                reason="Harps Community chat safety setup",
            )

        review_channel = discord.utils.get(
            category.text_channels, name=SAFETY_REVIEW_CHANNEL_NAME
        )
        if review_channel is None:
            review_channel = await guild.create_text_channel(
                SAFETY_REVIEW_CHANNEL_NAME,
                category=category,
                overwrites=staff_overwrites(guild),
                topic=safety_config_topic(SAFETY_DEFAULT_CONFIG),
                reason="Harps Community chat safety setup",
            )

        log_channel = discord.utils.get(
            category.text_channels, name=SAFETY_LOG_CHANNEL_NAME
        )
        if log_channel is None:
            log_channel = await guild.create_text_channel(
                SAFETY_LOG_CHANNEL_NAME,
                category=category,
                overwrites=staff_overwrites(guild),
                topic="Automatic chat safety detections and staff decisions",
                reason="Harps Community chat safety setup",
            )
        return category, review_channel, log_channel, role


async def get_safety_channel(
    guild: discord.Guild, channel_type: str, *, create_if_missing: bool = True
) -> discord.TextChannel | None:
    category = discord.utils.get(guild.categories, name=SAFETY_CATEGORY_NAME)
    channel_name = (
        SAFETY_REVIEW_CHANNEL_NAME
        if channel_type == "review"
        else SAFETY_LOG_CHANNEL_NAME
    )
    if category is not None:
        channel = discord.utils.get(category.text_channels, name=channel_name)
        if channel is not None or not create_if_missing:
            return channel
    elif not create_if_missing:
        return None

    _, review_channel, log_channel, _ = await ensure_safety_center(guild)
    return review_channel if channel_type == "review" else log_channel


async def send_safety_log(
    guild: discord.Guild,
    title: str,
    description: str,
    *,
    color: discord.Color = discord.Color.blurple(),
    fields: list[tuple[str, str, bool]] | None = None,
) -> bool:
    try:
        channel = await get_safety_channel(guild, "log")
        if channel is None:
            return False
        embed = discord.Embed(
            title=title,
            description=shortened(description, 4000),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        for name, value, inline in fields or []:
            embed.add_field(
                name=shortened(name, 250), value=shortened(value, 1024), inline=inline
            )
        embed.set_footer(text="Harps Community • Chat Safety Log")
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not save chat safety log in {guild.name}: {error}")
        return False


def lfg_public_overwrites(guild: discord.Guild) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            add_reactions=False,
            read_message_history=True,
            connect=True,
            speak=True,
        )
    }
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            read_message_history=True,
            connect=True,
            speak=True,
            move_members=True,
            manage_channels=True,
        )
    for role in guild.roles:
        if role.name in STAFF_ROLE_NAMES:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True,
                connect=True,
                speak=True,
                move_members=True,
            )
    return overwrites


async def ensure_lfg_hub(guild: discord.Guild) -> dict[str, discord.abc.GuildChannel]:
    lock = lfg_setup_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        overwrites = lfg_public_overwrites(guild)
        category = discord.utils.get(guild.categories, name=LFG_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(
                LFG_CATEGORY_NAME,
                overwrites=overwrites,
                reason="Harps Community LFG setup",
            )

        channels: dict[str, discord.abc.GuildChannel] = {"category": category}
        text_channel_settings = {
            "rules": (LFG_RULES_CHANNEL_NAME, "Rules and safety guidance for LFG posts"),
            "create": (LFG_CREATE_CHANNEL_NAME, "Create a new Harps Community LFG listing"),
            "active": (LFG_ACTIVE_CHANNEL_NAME, "Active team-finder listings"),
            "completed": (LFG_COMPLETED_CHANNEL_NAME, "Closed and expired LFG listings"),
        }
        for key, (name, topic) in text_channel_settings.items():
            channel = discord.utils.get(category.text_channels, name=name)
            if channel is None:
                channel = await guild.create_text_channel(
                    name,
                    category=category,
                    overwrites=overwrites,
                    topic=topic,
                    reason="Harps Community LFG setup",
                )
            channels[key] = channel

        log_channel = discord.utils.get(category.text_channels, name=LFG_LOG_CHANNEL_NAME)
        if log_channel is None:
            log_channel = await guild.create_text_channel(
                LFG_LOG_CHANNEL_NAME,
                category=category,
                overwrites=staff_overwrites(guild),
                topic="Private LFG creation, membership and closure logs",
                reason="Harps Community LFG setup",
            )
        channels["logs"] = log_channel

        voice_creator = discord.utils.get(
            category.voice_channels, name=LFG_VOICE_CREATOR_NAME
        )
        if voice_creator is None:
            voice_creator = await guild.create_voice_channel(
                LFG_VOICE_CREATOR_NAME,
                category=category,
                overwrites=overwrites,
                user_limit=0,
                reason="Harps Community LFG setup",
            )
        channels["voice"] = voice_creator
        return channels


async def get_lfg_channel(
    guild: discord.Guild, key: str, *, create_if_missing: bool = True
) -> discord.abc.GuildChannel | None:
    category = discord.utils.get(guild.categories, name=LFG_CATEGORY_NAME)
    names = {
        "rules": LFG_RULES_CHANNEL_NAME,
        "create": LFG_CREATE_CHANNEL_NAME,
        "active": LFG_ACTIVE_CHANNEL_NAME,
        "completed": LFG_COMPLETED_CHANNEL_NAME,
        "logs": LFG_LOG_CHANNEL_NAME,
        "voice": LFG_VOICE_CREATOR_NAME,
    }
    if category is not None and key in names:
        channel = discord.utils.get(category.channels, name=names[key])
        if channel is not None or not create_if_missing:
            return channel
    elif not create_if_missing:
        return None
    return (await ensure_lfg_hub(guild)).get(key)


async def send_lfg_log(
    guild: discord.Guild,
    title: str,
    description: str,
    *,
    color: discord.Color = discord.Color.blurple(),
    fields: list[tuple[str, str, bool]] | None = None,
) -> bool:
    try:
        channel = await get_lfg_channel(guild, "logs")
        if not isinstance(channel, discord.TextChannel):
            return False
        embed = discord.Embed(
            title=title,
            description=shortened(description, 4000),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        for name, value, inline in fields or []:
            embed.add_field(
                name=shortened(name, 250), value=shortened(value, 1024), inline=inline
            )
        embed.set_footer(text="Harps Community • LFG Log")
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not save LFG log in {guild.name}: {error}")
        return False


def is_antinuke_whitelisted(guild: discord.Guild, user: discord.abc.User) -> bool:
    if user.id in ANTINUKE_WHITELIST_IDS:
        return True
    if guild.owner_id == user.id or (bot.user is not None and bot.user.id == user.id):
        return True
    member = guild.get_member(user.id)
    return member is not None and any(
        role.name == ANTINUKE_WHITELIST_ROLE_NAME for role in member.roles
    )


async def ensure_antinuke_whitelist_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=ANTINUKE_WHITELIST_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=ANTINUKE_WHITELIST_ROLE_NAME,
            permissions=discord.Permissions.none(),
            reason="Harps Community anti-nuke setup",
        )
    return role


async def find_recent_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    *,
    target_id: int | None = None,
    attempts: int = 4,
) -> discord.AuditLogEntry | None:
    for attempt in range(attempts):
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age > 15:
                    continue
                entry_target_id = getattr(entry.target, "id", None)
                if target_id is None or entry_target_id == target_id:
                    return entry
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not read audit logs in {guild.name}: {error}")
            return None
        if attempt < attempts - 1:
            await asyncio.sleep(0.8)
    return None


def record_antinuke_action(
    guild_id: int, actor_id: int, action_name: str, weight: int = 1
) -> int:
    key = (guild_id, actor_id, action_name)
    timestamps = antinuke_activity[key]
    now = time.monotonic()
    cutoff = now - ANTINUKE_WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()
    timestamps.extend([now] * max(weight, 1))
    return len(timestamps)


async def punish_nuke_actor(
    guild: discord.Guild,
    actor: discord.abc.User,
    detection: str,
    details: str,
) -> bool:
    if is_antinuke_whitelisted(guild, actor):
        await send_server_log(
            guild,
            "antinuke",
            "🛡️ Whitelisted Action Ignored",
            f"{actor.mention} (`{actor.id}`) triggered **{detection}**, but is whitelisted.",
            color=discord.Color.green(),
            fields=[("Details", details, False)],
        )
        return False

    trigger_key = (guild.id, actor.id)
    if trigger_key in antinuke_triggered:
        return False
    antinuke_triggered.add(trigger_key)

    member = guild.get_member(actor.id)
    if member is not None and guild.me is not None and member.top_role >= guild.me.top_role:
        await send_server_log(
            guild,
            "antinuke",
            "🚨 Anti-Nuke Could Not Ban Actor",
            f"{actor.mention} (`{actor.id}`) triggered **{detection}**, but their role is above mine.",
            color=discord.Color.red(),
            fields=[("Details", details, False)],
        )
        return False

    try:
        await guild.ban(
            actor,
            reason=f"Anti-nuke: {detection} | {details}"[:512],
            delete_message_seconds=0,
        )
    except (discord.Forbidden, discord.HTTPException) as error:
        await send_server_log(
            guild,
            "antinuke",
            "🚨 Anti-Nuke Ban Failed",
            f"Failed to ban {actor.mention} (`{actor.id}`) after **{detection}**.",
            color=discord.Color.red(),
            fields=[("Details", details, False), ("Error", str(error), False)],
        )
        return False

    await send_server_log(
        guild,
        "antinuke",
        "🔨 Anti-Nuke Ban",
        f"{actor.mention} (`{actor.id}`) was automatically banned.",
        color=discord.Color.red(),
        fields=[("Detection", detection, True), ("Details", details, False)],
    )
    return True


async def check_mass_action(
    guild: discord.Guild,
    actor: discord.abc.User,
    action_name: str,
    detection: str,
    details: str,
    *,
    weight: int = 1,
) -> None:
    if is_antinuke_whitelisted(guild, actor):
        return
    count = record_antinuke_action(guild.id, actor.id, action_name, weight)
    if count >= ANTINUKE_MASS_THRESHOLD:
        await punish_nuke_actor(
            guild,
            actor,
            detection,
            f"{details} | {count} actions within {ANTINUKE_WINDOW_SECONDS} seconds",
        )


async def handle_unauthorized_bot_add(member: discord.Member) -> bool:
    if not member.bot:
        return False
    entry = await find_recent_audit_entry(
        member.guild, discord.AuditLogAction.bot_add, target_id=member.id
    )
    if entry is None or entry.user is None:
        await send_server_log(
            member.guild,
            "antinuke",
            "⚠️ Bot Addition Could Not Be Verified",
            f"{member.mention} (`{member.id}`) joined, but the inviter could not be read from Audit Logs.",
            color=discord.Color.orange(),
        )
        return False

    inviter = entry.user
    if is_antinuke_whitelisted(member.guild, inviter) or is_antinuke_whitelisted(
        member.guild, member
    ):
        await send_server_log(
            member.guild,
            "antinuke",
            "✅ Authorized Bot Added",
            f"{member.mention} (`{member.id}`) was added by {inviter.mention} (`{inviter.id}`).",
            color=discord.Color.green(),
        )
        return False

    bot_banned = False
    try:
        await member.guild.ban(
            member,
            reason=f"Anti-nuke: unauthorized bot added by {inviter} ({inviter.id})",
            delete_message_seconds=0,
        )
        bot_banned = True
    except (discord.Forbidden, discord.HTTPException) as error:
        await send_server_log(
            member.guild,
            "antinuke",
            "🚨 Unauthorized Bot Ban Failed",
            f"Could not ban {member.mention} (`{member.id}`).",
            color=discord.Color.red(),
            fields=[("Inviter", f"{inviter.mention} (`{inviter.id}`)", True), ("Error", str(error), False)],
        )

    await punish_nuke_actor(
        member.guild,
        inviter,
        "Unauthorized bot addition",
        f"Added bot {member} ({member.id}); bot banned: {bot_banned}",
    )
    return bot_banned


async def check_recent_member_removals(guild: discord.Guild, member_id: int) -> None:
    now = time.monotonic()
    removals = recent_member_removals[guild.id]
    removals.append((now, member_id))
    cutoff = now - ANTINUKE_WINDOW_SECONDS
    while removals and removals[0][0] < cutoff:
        removals.popleft()
    if len(removals) < ANTINUKE_MASS_THRESHOLD:
        return
    if now - last_member_removal_check.get(guild.id, 0.0) < 2.0:
        return
    last_member_removal_check[guild.id] = now

    recently_removed_ids = {removed_id for _, removed_id in removals}
    kick_counts: dict[int, tuple[discord.abc.User, int]] = {}
    try:
        async for entry in guild.audit_logs(limit=30):
            age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if age > ANTINUKE_WINDOW_SECONDS + 5:
                continue
            if entry.user is None:
                continue
            if entry.action == discord.AuditLogAction.kick:
                target_id = getattr(entry.target, "id", None)
                if target_id not in recently_removed_ids:
                    continue
                actor, count = kick_counts.get(entry.user.id, (entry.user, 0))
                kick_counts[entry.user.id] = (actor, count + 1)
            elif entry.action == discord.AuditLogAction.member_prune:
                removed_count = int(getattr(entry.extra, "members_removed", 0) or 0)
                if removed_count >= ANTINUKE_MASS_THRESHOLD:
                    await punish_nuke_actor(
                        guild,
                        entry.user,
                        "Mass member prune",
                        f"Pruned {removed_count} members",
                    )
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not inspect member removals in {guild.name}: {error}")
        return

    for actor, count in kick_counts.values():
        if count >= ANTINUKE_MASS_THRESHOLD:
            await punish_nuke_actor(
                guild,
                actor,
                "Mass member kicks",
                f"Kicked {count} members within {ANTINUKE_WINDOW_SECONDS} seconds",
            )


async def get_mod_log_channel(
    guild: discord.Guild, log_type: str, *, create_if_missing: bool = True
) -> discord.TextChannel | None:
    channel_name = MOD_LOG_CHANNELS.get(log_type, MOD_LOG_CHANNELS["server"])
    category = discord.utils.get(guild.categories, name=MOD_LOG_CATEGORY_NAME)
    if category is None:
        if not create_if_missing:
            return None
        category = await guild.create_category(
            MOD_LOG_CATEGORY_NAME,
            overwrites=staff_overwrites(guild),
            reason="Harps Community moderation logging setup",
        )

    channel = discord.utils.get(category.text_channels, name=channel_name)
    if channel is None and create_if_missing:
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=staff_overwrites(guild),
            topic=f"Harps Community {channel_name.replace('-', ' ')}",
            reason="Harps Community moderation logging setup",
        )
    return channel


async def send_mod_log(
    guild: discord.Guild,
    log_type: str,
    title: str,
    moderator: discord.Member,
    *,
    target: discord.Member | discord.User | None = None,
    reason: str = "No reason provided",
    details: str | None = None,
    color: discord.Color = discord.Color.orange(),
) -> bool:
    try:
        channel = await get_mod_log_channel(guild, log_type)
        if channel is None:
            return False
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Moderator",
            value=f"{moderator.mention}\n`{moderator.id}`",
            inline=True,
        )
        if target is not None:
            embed.add_field(
                name="Member",
                value=f"{target.mention}\n`{target.id}`",
                inline=True,
            )
        embed.add_field(name="Reason", value=reason[:1024], inline=False)
        if details:
            embed.add_field(name="Details", value=details[:1024], inline=False)
        embed.set_footer(text="Harps Community • Moderation Log")
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not save moderation log in {guild.name}: {error}")
        return False


def moderation_block_reason(
    ctx: commands.Context, target: discord.Member
) -> str | None:
    if target == ctx.author:
        return "You cannot use this moderation command on yourself."
    if target == ctx.guild.owner:
        return "The server owner cannot be moderated."
    if target == ctx.guild.me:
        return "I cannot moderate myself."
    if ctx.author != ctx.guild.owner and target.top_role >= ctx.author.top_role:
        return "You cannot moderate a member with an equal or higher role than yours."
    if ctx.guild.me is None or target.top_role >= ctx.guild.me.top_role:
        return "My role must be higher than the member's highest role."
    return None


def parse_timeout_duration(value: str) -> timedelta | None:
    match = re.fullmatch(r"(\d+)([mhd])", value.lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    duration = {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }[unit]
    if duration <= timedelta(0) or duration > timedelta(days=28):
        return None
    return duration


async def give_regular_role(member: discord.Member) -> bool:
    """Give the configured Regulars role to a human member when possible."""
    if member.bot:
        return False
    role = discord.utils.get(member.guild.roles, name=AUTO_ROLE_NAME)
    if role is None or role in member.roles:
        return False
    bot_member = member.guild.me
    if bot_member is None or role >= bot_member.top_role:
        raise RuntimeError(
            f"The {AUTO_ROLE_NAME} role must be below the bot's highest role."
        )
    await member.add_roles(role, reason="Harps Community automatic member role")
    return True


async def sync_regular_roles(guild: discord.Guild, reason: str) -> tuple[int, int]:
    role = discord.utils.get(guild.roles, name=AUTO_ROLE_NAME)
    if role is None:
        return 0, 0
    if guild.me is None or role >= guild.me.top_role:
        raise RuntimeError(
            f"The {AUTO_ROLE_NAME} role must be below the bot's highest role."
        )

    updated = 0
    failed = 0
    for member in guild.members:
        if member.bot or role in member.roles:
            continue
        try:
            await member.add_roles(role, reason=reason)
            updated += 1
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    return updated, failed


async def update_member_count(
    guild: discord.Guild, *, create_if_missing: bool = False
) -> discord.VoiceChannel | None:
    """Create or refresh the server's read-only member counter channel."""
    category = discord.utils.get(guild.categories, name=SERVER_STATS_CATEGORY_NAME)
    channel = discord.utils.find(
        lambda item: item.name.startswith(MEMBER_COUNT_CHANNEL_PREFIX),
        category.voice_channels if category else guild.voice_channels,
    )

    if channel is None and not create_if_missing:
        return None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, connect=False
        )
    }
    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True, connect=True, manage_channels=True
        )

    if category is None:
        category = await guild.create_category(
            SERVER_STATS_CATEGORY_NAME,
            overwrites=overwrites,
            reason="Harps Community server statistics setup",
        )

    member_total = guild.member_count or len(guild.members)
    expected_name = f"{MEMBER_COUNT_CHANNEL_PREFIX} {member_total}"
    if channel is None:
        channel = await guild.create_voice_channel(
            expected_name,
            category=category,
            overwrites=overwrites,
            reason="Harps Community member counter setup",
        )
    elif channel.name != expected_name:
        await channel.edit(
            name=expected_name,
            reason="Harps Community member count changed",
        )
    return channel


async def get_ticket_log_channel(
    guild: discord.Guild, ticket_type: str
) -> discord.TextChannel:
    type_label, log_channel_name = TICKET_TYPES.get(
        ticket_type, (ticket_type.title(), "other-ticket-logs")
    )
    overwrites = staff_overwrites(guild)
    category = discord.utils.get(guild.categories, name=TICKET_LOG_CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(
            TICKET_LOG_CATEGORY_NAME,
            overwrites=overwrites,
            reason="Harps Community ticket logging setup",
        )

    channel = discord.utils.get(category.text_channels, name=log_channel_name)
    if channel is None:
        channel = await guild.create_text_channel(
            log_channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Closed {type_label} ticket transcripts and audit logs",
            reason="Harps Community ticket logging setup",
        )
    return channel


async def build_ticket_transcript(channel: discord.TextChannel) -> tuple[bytes, int]:
    lines = [
        "HARPS COMMUNITY TICKET TRANSCRIPT",
        f"Channel: #{channel.name} ({channel.id})",
        f"Created: {discord.utils.format_dt(channel.created_at, style='F')}",
        "=" * 72,
        "",
    ]
    message_count = 0
    async for message in channel.history(limit=None, oldest_first=True):
        message_count += 1
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(
            f"[{timestamp}] {message.author} ({message.author.id}): "
            f"{message.clean_content or '[no text content]'}"
        )
        for attachment in message.attachments:
            lines.append(f"    Attachment: {attachment.filename} — {attachment.url}")
        for embed in message.embeds:
            lines.append(
                f"    Embed: {embed.title or '[no title]'} — "
                f"{embed.description or '[no description]'}"
            )
        if message.edited_at:
            lines.append(
                f"    Edited: {message.edited_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        lines.append("")
    return "\n".join(lines).encode("utf-8"), message_count


async def log_closed_ticket(
    channel: discord.TextChannel, closed_by: discord.Member | discord.User
) -> None:
    creator_id = ticket_creator_id(channel)
    ticket_type = ticket_type_from_channel(channel) or "other"
    type_label = TICKET_TYPES.get(ticket_type, (ticket_type.title(), ""))[0]
    transcript, message_count = await build_ticket_transcript(channel)
    log_channel = await get_ticket_log_channel(channel.guild, ticket_type)

    embed = discord.Embed(
        title="🔒 Ticket Closed",
        description="A complete transcript is attached to this log entry.",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Ticket category", value=type_label, inline=True)
    embed.add_field(name="Ticket channel", value=f"#{channel.name}\n`{channel.id}`", inline=True)
    embed.add_field(
        name="Ticket creator",
        value=f"<@{creator_id}>\n`{creator_id}`" if creator_id else "Unknown",
        inline=True,
    )
    embed.add_field(
        name="Closed by",
        value=f"{closed_by.mention}\n`{closed_by.id}`",
        inline=True,
    )
    embed.add_field(
        name="Opened",
        value=discord.utils.format_dt(channel.created_at, style="F"),
        inline=True,
    )
    embed.add_field(
        name="Closed",
        value=discord.utils.format_dt(discord.utils.utcnow(), style="F"),
        inline=True,
    )
    embed.add_field(name="Messages recorded", value=str(message_count), inline=True)
    embed.add_field(name="Topic metadata", value=f"`{channel.topic or 'None'}`", inline=False)
    embed.set_footer(text="Harps Community • Ticket Audit Log")

    transcript_file = discord.File(
        io.BytesIO(transcript), filename=f"transcript-{channel.name}-{channel.id}.txt"
    )
    await log_channel.send(embed=embed, file=transcript_file)


async def send_welcome(member: discord.Member) -> bool:
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel is None:
        return False

    rules_channel = discord.utils.get(
        member.guild.text_channels, name=RULES_CHANNEL_NAME
    )
    member_total = member.guild.member_count or len(member.guild.members)
    rules_destination = (
        rules_channel.mention
        if rules_channel is not None
        else f"the `{RULES_CHANNEL_NAME}` channel"
    )
    embed = discord.Embed(
        title="✨ Welcome to Harps Community!",
        description=(
            f"Hey {member.mention}, we’re excited to have you here! 🎉\n\n"
            f"You are officially member **#{member_total:,}** of **{member.guild.name}**. "
            "Take a moment to get comfortable, meet the community and enjoy your stay."
        ),
        color=discord.Color.from_rgb(255, 112, 67),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="📚 Start with the rules",
        value=(
            f"Please read {rules_destination} before chatting. "
            "The button below will take you straight there."
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Join the community",
        value="Say hello, join the conversations and make yourself at home!",
        inline=False,
    )
    embed.add_field(
        name="🎫 Need help?",
        value="Open a support ticket at any time and the Harps Community team will assist you.",
        inline=False,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if member.guild.icon is not None:
        embed.set_author(
            name=member.guild.name,
            icon_url=member.guild.icon.url,
        )
    banner_url = server_banner_url(member.guild)
    if banner_url is not None:
        embed.set_image(url=banner_url)
    embed.set_footer(
        text=f"Harps Community • Member #{member_total:,} • Welcome aboard!"
    )

    view = None
    if rules_channel is not None:
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Read the Rules",
                emoji="📚",
                style=discord.ButtonStyle.link,
                url=(
                    f"https://discord.com/channels/{member.guild.id}/"
                    f"{rules_channel.id}"
                ),
            )
        )

    await channel.send(content=f"🎉 {member.mention}", embed=embed, view=view)
    return True


async def send_goodbye(member: discord.Member) -> bool:
    channel = discord.utils.get(member.guild.text_channels, name=GOODBYE_CHANNEL_NAME)
    if channel is None:
        return False

    member_total = member.guild.member_count or len(member.guild.members)
    time_with_server = "Unknown"
    if member.joined_at is not None:
        days = max((discord.utils.utcnow() - member.joined_at).days, 0)
        time_with_server = f"{days} day{'s' if days != 1 else ''}"

    embed = discord.Embed(
        title="🌙 Until Next Time...",
        description=(
            f"**{member.display_name}** has left **{member.guild.name}**.\n\n"
            "Thank you for being part of Harps Community. The door is always open, "
            "and we hope our paths cross again someday. 👋"
        ),
        color=discord.Color.from_rgb(126, 87, 194),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="🕒 Time with us", value=time_with_server, inline=True)
    embed.add_field(name="👥 Members remaining", value=f"{member_total:,}", inline=True)
    embed.add_field(
        name="💜 From Harps Community",
        value="Thank you for the memories, conversations and moments you shared with us.",
        inline=False,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if member.guild.icon is not None:
        embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url)
    banner_url = server_banner_url(member.guild)
    if banner_url is not None:
        embed.set_image(url=banner_url)
    embed.set_footer(text="Harps Community • Farewell and take care!")
    await channel.send(embed=embed)
    return True


def role_is_safe_to_request(guild: discord.Guild, role: discord.Role) -> bool:
    if role.is_default() or role.managed:
        return False
    if role.name in STAFF_ROLE_NAMES or role.name in {
        AUTO_ROLE_NAME,
        ANTINUKE_WHITELIST_ROLE_NAME,
    }:
        return False
    if ROLE_REQUEST_ALLOWED_ROLE_NAMES and role.name not in ROLE_REQUEST_ALLOWED_ROLE_NAMES:
        return False
    permissions = role.permissions
    if any(
        (
            permissions.administrator,
            permissions.manage_guild,
            permissions.manage_roles,
            permissions.manage_channels,
            permissions.manage_webhooks,
            permissions.ban_members,
            permissions.kick_members,
            permissions.moderate_members,
            permissions.manage_messages,
            permissions.mention_everyone,
        )
    ):
        return False
    return guild.me is not None and role < guild.me.top_role


def requestable_roles(
    guild: discord.Guild, member: discord.Member
) -> list[discord.Role]:
    roles = [
        role
        for role in guild.roles
        if role not in member.roles and role_is_safe_to_request(guild, role)
    ]
    return sorted(roles, key=lambda role: role.name.casefold())[:25]


def role_request_details(channel: discord.TextChannel) -> tuple[int, int] | None:
    match = re.search(
        r"harps-role-request:user=(\d+);role=(\d+)", channel.topic or ""
    )
    return (int(match.group(1)), int(match.group(2))) if match else None


async def create_role_request(
    interaction: discord.Interaction, role_id: int
) -> None:
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Role requests can only be opened inside the server.", ephemeral=True
        )
        return
    role = guild.get_role(role_id)
    if role is None or role in interaction.user.roles or not role_is_safe_to_request(
        guild, role
    ):
        await interaction.response.send_message(
            "That role is no longer available to request.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    lock_key = (guild.id, interaction.user.id)
    lock = role_request_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        existing = discord.utils.find(
            lambda item: (item.topic or "").startswith(
                f"harps-role-request:user={interaction.user.id};"
            ),
            guild.text_channels,
        )
        if existing is not None:
            await interaction.followup.send(
                f"You already have an open role request: {existing.mention}",
                ephemeral=True,
            )
            return

        overwrites = staff_overwrites(guild)
        overwrites[interaction.user] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        )
        category = discord.utils.get(guild.categories, name=ROLE_REQUEST_CATEGORY_NAME)
        try:
            if category is None:
                category = await guild.create_category(
                    ROLE_REQUEST_CATEGORY_NAME,
                    overwrites=staff_overwrites(guild),
                    reason="Harps Community role request setup",
                )
            safe_name = re.sub(r"[^a-z0-9-]", "-", interaction.user.name.lower())
            safe_name = re.sub(r"-+", "-", safe_name).strip("-") or "member"
            channel = await guild.create_text_channel(
                f"role-request-{safe_name}"[:100],
                category=category,
                overwrites=overwrites,
                topic=f"harps-role-request:user={interaction.user.id};role={role.id}",
                reason=f"Role request opened by {interaction.user} ({interaction.user.id})",
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            await interaction.followup.send(
                f"I could not create the private request channel: `{error}`",
                ephemeral=True,
            )
            return
        finally:
            role_request_locks.pop(lock_key, None)

        embed = discord.Embed(
            title="🎭 New Role Request",
            description=(
                f"{interaction.user.mention} is requesting {role.mention}.\n\n"
                "The member may add any helpful context in this private channel. "
                "Authorized staff can approve or deny the request below."
            ),
            color=role.color if role.color.value else discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Member",
            value=f"{interaction.user.mention}\n`{interaction.user.id}`",
            inline=True,
        )
        embed.add_field(name="Requested role", value=f"{role.mention}\n`{role.id}`", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Harps Community • Role Request Review")
        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=RoleRequestDecisionView(),
        )
        await interaction.followup.send(
            f"✅ Your private role request is ready: {channel.mention}", ephemeral=True
        )


class RoleRequestSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role]):
        self.role_ids = {str(role.id): role.id for role in roles}
        options = [
            discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                description="Request this role from the staff team",
                emoji="🎭",
            )
            for role in roles
        ]
        super().__init__(
            placeholder="Choose the role you want to request...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="harps:role_request:select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await create_role_request(interaction, int(self.values[0]))


class RoleRequestSelectView(discord.ui.View):
    def __init__(self, roles: list[discord.Role]):
        super().__init__(timeout=120)
        self.add_item(RoleRequestSelect(roles))


class RoleRequestPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Request a Role",
        style=discord.ButtonStyle.primary,
        emoji="🎭",
        custom_id="harps:role_request:open",
    )
    async def open_request(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            await interaction.response.send_message(
                "This panel only works inside the server.", ephemeral=True
            )
            return
        roles = requestable_roles(interaction.guild, interaction.user)
        if not roles:
            await interaction.response.send_message(
                "There are no safe roles available for you to request right now.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Choose the role you would like the staff team to review:",
            view=RoleRequestSelectView(roles),
            ephemeral=True,
        )


class RoleRequestDecisionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and is_staff(interaction.user):
            return True
        await interaction.response.send_message(
            "Only authorized Harps Community staff can review role requests.",
            ephemeral=True,
        )
        return False

    async def finish_request(
        self, interaction: discord.Interaction, *, approved: bool
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This is not a role request channel.", ephemeral=True
            )
            return
        details = role_request_details(channel)
        if details is None:
            await interaction.response.send_message(
                "This request has invalid or missing metadata.", ephemeral=True
            )
            return
        lock = role_decision_locks.setdefault(channel.id, asyncio.Lock())
        if lock.locked():
            await interaction.response.send_message(
                "Another staff member is already processing this request.", ephemeral=True
            )
            return

        async with lock:
            requester_id, role_id = details
            member = channel.guild.get_member(requester_id)
            role = channel.guild.get_role(role_id)
            if member is None or role is None:
                await interaction.response.send_message(
                    "The member or requested role no longer exists.", ephemeral=True
                )
                return

            if approved:
                if not role_is_safe_to_request(channel.guild, role):
                    await interaction.response.send_message(
                        "This role is no longer safe or assignable, so the request was not approved.",
                        ephemeral=True,
                    )
                    return
                try:
                    await member.add_roles(
                        role,
                        reason=f"Role request approved by {interaction.user} ({interaction.user.id})",
                    )
                except (discord.Forbidden, discord.HTTPException) as error:
                    await interaction.response.send_message(
                        f"I could not assign the role: `{error}`", ephemeral=True
                    )
                    return
                result = f"✅ {member.mention}'s request for {role.mention} was approved by {interaction.user.mention}."
                title = "✅ Role Request Approved"
                color = discord.Color.green()
            else:
                result = f"❌ {member.mention}'s request for {role.mention} was denied by {interaction.user.mention}."
                title = "❌ Role Request Denied"
                color = discord.Color.red()

            await interaction.response.send_message(result)
            await send_server_log(
                channel.guild,
                "role",
                title,
                result,
                color=color,
                fields=[
                    ("Member ID", str(member.id), True),
                    ("Role ID", str(role.id), True),
                    ("Reviewed by", f"{interaction.user} (`{interaction.user.id}`)", False),
                ],
            )
            await asyncio.sleep(5)
            try:
                await channel.delete(
                    reason=f"Role request {'approved' if approved else 'denied'} by {interaction.user}"
                )
            except discord.NotFound:
                pass
            finally:
                role_decision_locks.pop(channel.id, None)

    @discord.ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="harps:role_request:accept",
    )
    async def accept(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish_request(interaction, approved=True)

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="harps:role_request:deny",
    )
    async def deny(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish_request(interaction, approved=False)


class BoostPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Boost the Server",
        style=discord.ButtonStyle.primary,
        emoji="🚀",
        custom_id="harps:server:boost",
    )
    async def boost_server(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This button only works inside Harps Community.", ephemeral=True
            )
            return
        link_view = discord.ui.View()
        link_view.add_item(
            discord.ui.Button(
                label="Discord Boosting Help",
                style=discord.ButtonStyle.link,
                emoji="💎",
                url="https://support.discord.com/hc/en-us/articles/360028038352-Server-Boosting-FAQ",
            )
        )
        embed = discord.Embed(
            title="🚀 Ready to Boost Harps Community?",
            description=(
                "Thank you for supporting our community! Discord requires boosts to be "
                "confirmed from its built-in **Server Boost** screen."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="🖥️ Desktop / Browser",
            value=(
                "Open **Harps Community**, then click **Server Boost** above the channel "
                "list—or click the server name and choose **Server Boost**."
            ),
            inline=False,
        )
        embed.add_field(
            name="📱 Mobile",
            value=(
                "Tap the **Harps Community** name at the top, then choose "
                "**Boost Server** or **Server Boost**."
            ),
            inline=False,
        )
        await interaction.response.send_message(
            embed=embed, view=link_view, ephemeral=True
        )


class CloseConfirmationView(discord.ui.View):
    def __init__(self, requester_id: int):
        super().__init__(timeout=60)
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "Only the person who requested closure can use these buttons.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Ticket closure cancelled.", view=self
        )
        self.stop()

    @discord.ui.button(
        label="Confirm Close", style=discord.ButtonStyle.danger, emoji="🔒"
    )
    async def confirm_close(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "This button can only be used in a ticket channel.", ephemeral=True
            )
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🔒 Saving the complete ticket log and transcript...", view=self
        )
        self.stop()
        try:
            await log_closed_ticket(interaction.channel, interaction.user)
        except (discord.Forbidden, discord.HTTPException) as error:
            await interaction.edit_original_response(
                content=(
                    "❌ I could not save the ticket log, so this channel was not deleted. "
                    "Please check my Manage Channels, View Channel, Send Messages, "
                    f"Attach Files, and Read Message History permissions. (`{error}`)"
                ),
                view=self,
            )
            return

        await interaction.edit_original_response(
            content="✅ Ticket logged successfully. This channel will be deleted in 5 seconds.",
            view=self,
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(
                reason=f"Ticket closed by {interaction.user} ({interaction.user.id})"
            )
        except discord.NotFound:
            pass


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="harps:ticket:close",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or ticket_creator_id(channel) is None:
            await interaction.response.send_message(
                "This is not a recognized ticket channel.", ephemeral=True
            )
            return

        creator_id = ticket_creator_id(channel)
        if interaction.user.id != creator_id and not is_staff(interaction.user):
            await interaction.response.send_message(
                "Only the ticket creator or an authorized staff member can close this ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Are you sure you want to close this ticket?",
            view=CloseConfirmationView(interaction.user.id),
            ephemeral=True,
        )


async def create_ticket(
    interaction: discord.Interaction, ticket_type: str, display_name: str
) -> None:
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Tickets can only be created inside the server.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    lock_key = (guild.id, interaction.user.id, ticket_type)
    lock = ticket_creation_locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        expected_topic = ticket_topic(interaction.user.id, ticket_type)
        existing = discord.utils.find(
            lambda channel: channel.topic == expected_topic, guild.text_channels
        )
        if existing is not None:
            await interaction.followup.send(
                f"You already have an open **{display_name}** ticket: {existing.mention}",
                ephemeral=True,
            )
            return

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        staff_roles = [role for role in guild.roles if role.name in STAFF_ROLE_NAMES]
        bot_member = guild.me
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
        }
        if bot_member is not None:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            )
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )

        try:
            if category is None:
                category = await guild.create_category(
                    TICKET_CATEGORY_NAME,
                    overwrites=overwrites,
                    reason="Harps Community ticket system setup",
                )

            safe_name = re.sub(r"[^a-z0-9-]", "-", interaction.user.name.lower())
            safe_name = re.sub(r"-+", "-", safe_name).strip("-") or "member"
            channel = await guild.create_text_channel(
                name=f"{ticket_type}-{safe_name}"[:100],
                category=category,
                topic=expected_topic,
                overwrites=overwrites,
                reason=f"{display_name} ticket opened by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I could not create the ticket. Please ask an administrator to give me "
                "Manage Channels and Manage Roles permissions.",
                ephemeral=True,
            )
            return
        finally:
            ticket_creation_locks.pop(lock_key, None)

        embed = discord.Embed(
            title="🎫 Harps Community Support",
            description=(
                f"Welcome, {interaction.user.mention}!\n\n"
                f"**Ticket type:** {display_name}\n"
                "Please explain what you need help with. A member of our support team "
                "will assist you as soon as possible."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Before you begin",
            value="Include any relevant details or screenshots so we can help quickly.",
            inline=False,
        )
        embed.set_footer(text="Harps Community • Support Team")
        await channel.send(
            content=interaction.user.mention, embed=embed, view=CloseTicketView()
        )
        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="General Support",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="harps:ticket:create:general",
    )
    async def general_support(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await create_ticket(interaction, "general", "General Support")

    @discord.ui.button(
        label="Report a Member",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="harps:ticket:create:report",
    )
    async def report_member(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await create_ticket(interaction, "report", "Report a Member")

    @discord.ui.button(
        label="Partnership / Other",
        style=discord.ButtonStyle.secondary,
        emoji="🤝",
        custom_id="harps:ticket:create:partnership",
    )
    async def partnership(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await create_ticket(interaction, "partnership", "Partnership / Other")


def prune_safety_timestamps(
    timestamps: deque[float], now: float, window_seconds: int
) -> int:
    while timestamps and now - timestamps[0] > window_seconds:
        timestamps.popleft()
    return len(timestamps)


def safety_review_metadata(message: discord.Message) -> dict[str, int | str] | None:
    if not message.embeds:
        return None
    footer = message.embeds[0].footer.text or ""
    match = re.fullmatch(
        r"harps-safety:guild=(\d+);user=(\d+);source=(\d+);reason=([a-z_]+)",
        footer,
    )
    if match is None:
        return None
    return {
        "guild_id": int(match.group(1)),
        "user_id": int(match.group(2)),
        "source_id": int(match.group(3)),
        "reason": match.group(4),
    }


def safety_review_is_pending(message: discord.Message) -> bool:
    if not message.embeds:
        return False
    return any(
        field.name == "Status" and field.value.startswith("⏳ Pending")
        for field in message.embeds[0].fields
    )


async def refresh_review_message(message: discord.Message) -> discord.Message:
    try:
        return await message.channel.fetch_message(message.id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return message


async def finish_safety_review(
    message: discord.Message,
    moderator: discord.Member,
    action: str,
    color: discord.Color,
) -> None:
    if not message.embeds:
        return
    embed = discord.Embed.from_dict(message.embeds[0].to_dict())
    status = (
        f"✅ **{action}**\nBy {moderator.mention} (`{moderator.id}`)\n"
        f"{discord.utils.format_dt(discord.utils.utcnow(), style='F')}"
    )
    for index, field in enumerate(embed.fields):
        if field.name == "Status":
            embed.set_field_at(index, name="Status", value=status, inline=False)
            break
    embed.color = color
    await message.edit(embed=embed, view=SafetyReviewView(disabled=True))


async def send_safety_review(
    message: discord.Message,
    reason_code: str,
    reason_name: str,
    evidence: str,
) -> bool:
    try:
        review_channel = await get_safety_channel(message.guild, "review")
        if review_channel is None:
            return False
        embed = discord.Embed(
            title="🔎 Chat Safety Review Required",
            description=(
                "The message was removed as a precaution, but **no punishment was "
                "applied**. Staff can review the evidence and choose an action below."
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Member",
            value=f"{message.author.mention}\n`{message.author.id}`",
            inline=True,
        )
        embed.add_field(
            name="Channel",
            value=f"{message.channel.mention}\n`{message.channel.id}`",
            inline=True,
        )
        embed.add_field(name="Detection", value=reason_name, inline=False)
        embed.add_field(name="Evidence", value=shortened(evidence, 1024), inline=False)
        embed.add_field(name="Source message ID", value=f"`{message.id}`", inline=False)
        embed.add_field(
            name="Status",
            value="⏳ Pending staff review",
            inline=False,
        )
        embed.set_footer(
            text=(
                f"harps-safety:guild={message.guild.id};user={message.author.id};"
                f"source={message.id};reason={reason_code}"
            )
        )
        await review_channel.send(embed=embed, view=SafetyReviewView())
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not create safety review in {message.guild.name}: {error}")
        return False


def safety_target_block_reason(
    guild: discord.Guild,
    moderator: discord.Member,
    member: discord.Member,
) -> str | None:
    if member.id == guild.owner_id:
        return "The server owner cannot be punished."
    if bot.user is not None and member.id == bot.user.id:
        return "I cannot punish myself."
    if member.id == moderator.id:
        return "You cannot use a review action on yourself."
    if is_safety_whitelisted(member):
        return "That member is now staff or safety-whitelisted."
    if guild.me is None or member.top_role >= guild.me.top_role:
        return "Move my bot role above the member's highest role first."
    if moderator.id != guild.owner_id and member.top_role >= moderator.top_role:
        return "You cannot moderate a member with an equal or higher role."
    return None


async def safety_review_context(
    interaction: discord.Interaction,
    required_permission: str,
) -> tuple[discord.Message, dict[str, int | str], discord.Member] | None:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This safety action can only be used in the server.", ephemeral=True
        )
        return None
    if not is_staff(interaction.user):
        await interaction.response.send_message(
            "Only authorized Harps Community staff can review this incident.",
            ephemeral=True,
        )
        return None
    if not getattr(interaction.user.guild_permissions, required_permission, False):
        await interaction.response.send_message(
            f"You need the `{required_permission}` permission for that action.",
            ephemeral=True,
        )
        return None
    if interaction.message is None:
        await interaction.response.send_message(
            "I could not find the review message.", ephemeral=True
        )
        return None
    message = await refresh_review_message(interaction.message)
    metadata = safety_review_metadata(message)
    if metadata is None or int(metadata["guild_id"]) != interaction.guild.id:
        await interaction.response.send_message(
            "This review card is invalid or incomplete.", ephemeral=True
        )
        return None
    if not safety_review_is_pending(message):
        await interaction.response.send_message(
            "This incident has already been reviewed.", ephemeral=True
        )
        return None
    return message, metadata, interaction.user


class SafetyBanConfirmationView(discord.ui.View):
    def __init__(
        self,
        review_message: discord.Message,
        target_id: int,
        moderator_id: int,
        reason_code: str,
    ):
        super().__init__(timeout=30)
        self.review_message = review_message
        self.target_id = target_id
        self.moderator_id = moderator_id
        self.reason_code = reason_code

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.moderator_id:
            await interaction.response.send_message(
                "Only the staff member who opened this confirmation can use it.",
                ephemeral=True,
            )
            return False
        if not isinstance(interaction.user, discord.Member) or not is_staff(
            interaction.user
        ):
            await interaction.response.send_message(
                "You are no longer authorized to use this action.", ephemeral=True
            )
            return False
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "You need the `ban_members` permission for that action.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Ban cancelled.", view=None)

    @discord.ui.button(label="Confirm Ban", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This action can only be used in the server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = safety_review_action_locks.setdefault(
            self.review_message.id, asyncio.Lock()
        )
        async with lock:
            review_message = await refresh_review_message(self.review_message)
            if not safety_review_is_pending(review_message):
                await interaction.followup.send(
                    "This incident has already been reviewed.", ephemeral=True
                )
                return

            member = interaction.guild.get_member(self.target_id)
            if member is not None:
                blocked = safety_target_block_reason(
                    interaction.guild, interaction.user, member
                )
                if blocked:
                    await interaction.followup.send(blocked, ephemeral=True)
                    return
            try:
                await interaction.guild.ban(
                    member or discord.Object(id=self.target_id),
                    reason=(
                        f"Chat safety review: {self.reason_code.replace('_', ' ')} | "
                        f"Moderator: {interaction.user} ({interaction.user.id})"
                    ),
                    delete_message_seconds=0,
                )
            except (discord.Forbidden, discord.HTTPException) as error:
                await interaction.followup.send(
                    f"I could not ban that member: `{error}`", ephemeral=True
                )
                return

            await finish_safety_review(
                review_message, interaction.user, "Member banned", discord.Color.red()
            )
            await send_safety_log(
                interaction.guild,
                "🔨 Safety Review: Member Banned",
                (
                    f"<@{self.target_id}> (`{self.target_id}`) was banned by "
                    f"{interaction.user.mention} after staff review."
                ),
                color=discord.Color.red(),
                fields=[
                    ("Detection", self.reason_code.replace("_", " ").title(), False),
                    ("Review card", f"`{review_message.id}`", False),
                ],
            )
            if member is not None:
                await send_mod_log(
                    interaction.guild,
                    "ban",
                    "🔨 Member Banned from Safety Review",
                    interaction.user,
                    target=member,
                    reason=self.reason_code.replace("_", " ").title(),
                )
            await interaction.followup.send(
                f"🔨 <@{self.target_id}> was banned and the review was closed.",
                ephemeral=True,
            )


class SafetyReviewView(discord.ui.View):
    def __init__(self, *, disabled: bool = False):
        super().__init__(timeout=None)
        if disabled:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(
        label="Dismiss",
        style=discord.ButtonStyle.secondary,
        emoji="✅",
        custom_id="harps:safety:review:dismiss",
    )
    async def dismiss(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await safety_review_context(interaction, "manage_messages")
        if context is None:
            return
        message, metadata, moderator = context
        await interaction.response.defer(ephemeral=True)
        lock = safety_review_action_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            message = await refresh_review_message(message)
            if not safety_review_is_pending(message):
                await interaction.followup.send(
                    "This incident has already been reviewed.", ephemeral=True
                )
                return
            await finish_safety_review(
                message, moderator, "Dismissed — no punishment", discord.Color.green()
            )
            await send_safety_log(
                interaction.guild,
                "✅ Safety Review Dismissed",
                (
                    f"Incident for <@{metadata['user_id']}> (`{metadata['user_id']}`) "
                    f"was dismissed by {moderator.mention}."
                ),
                color=discord.Color.green(),
                fields=[
                    ("Detection", str(metadata["reason"]).replace("_", " ").title(), False),
                    ("Review card", f"`{message.id}`", False),
                ],
            )
        await interaction.followup.send(
            "✅ Review dismissed with no member punishment.", ephemeral=True
        )

    @discord.ui.button(
        label="Warn",
        style=discord.ButtonStyle.primary,
        emoji="⚠️",
        custom_id="harps:safety:review:warn",
    )
    async def warn_member(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await safety_review_context(interaction, "manage_messages")
        if context is None:
            return
        message, metadata, moderator = context
        target_id = int(metadata["user_id"])
        member = interaction.guild.get_member(target_id)
        if member is None:
            await interaction.response.send_message(
                "That member is no longer in the server. You can dismiss or ban the review.",
                ephemeral=True,
            )
            return
        if is_safety_whitelisted(member):
            await interaction.response.send_message(
                "That member is now staff or safety-whitelisted.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = safety_review_action_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            message = await refresh_review_message(message)
            if not safety_review_is_pending(message):
                await interaction.followup.send(
                    "This incident has already been reviewed.", ephemeral=True
                )
                return
            reason = str(metadata["reason"]).replace("_", " ").title()
            try:
                await member.send(
                    f"⚠️ You received a chat safety warning in **{interaction.guild.name}**.\n"
                    f"Reason: {reason}"
                )
                dm_status = "Warning delivered by DM"
            except (discord.Forbidden, discord.HTTPException):
                dm_status = "DM could not be delivered"
            await finish_safety_review(
                message, moderator, f"Member warned ({dm_status})", discord.Color.gold()
            )
            await send_safety_log(
                interaction.guild,
                "⚠️ Safety Review: Member Warned",
                f"{member.mention} (`{member.id}`) was warned by {moderator.mention}.",
                color=discord.Color.gold(),
                fields=[("Detection", reason, False), ("Delivery", dm_status, False)],
            )
            await send_mod_log(
                interaction.guild,
                "server",
                "⚠️ Member Warned from Safety Review",
                moderator,
                target=member,
                reason=reason,
                details=dm_status,
                color=discord.Color.gold(),
            )
        await interaction.followup.send(
            f"⚠️ {member.mention} was warned and the review was closed.", ephemeral=True
        )

    @discord.ui.button(
        label="Timeout",
        style=discord.ButtonStyle.danger,
        emoji="⏳",
        custom_id="harps:safety:review:timeout",
    )
    async def timeout_member(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await safety_review_context(interaction, "moderate_members")
        if context is None:
            return
        message, metadata, moderator = context
        member = interaction.guild.get_member(int(metadata["user_id"]))
        if member is None:
            await interaction.response.send_message(
                "That member is no longer in the server.", ephemeral=True
            )
            return
        blocked = safety_target_block_reason(interaction.guild, moderator, member)
        if blocked:
            await interaction.response.send_message(blocked, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        lock = safety_review_action_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            message = await refresh_review_message(message)
            if not safety_review_is_pending(message):
                await interaction.followup.send(
                    "This incident has already been reviewed.", ephemeral=True
                )
                return
            config = safety_config_from_channel(
                await get_safety_channel(interaction.guild, "review", create_if_missing=False)
            )
            minutes = config["timeout_minutes"]
            until = discord.utils.utcnow() + timedelta(minutes=minutes)
            reason = str(metadata["reason"]).replace("_", " ").title()
            try:
                await member.timeout(
                    until,
                    reason=(
                        f"Chat safety review: {reason} | "
                        f"Moderator: {moderator} ({moderator.id})"
                    ),
                )
            except (discord.Forbidden, discord.HTTPException) as error:
                await interaction.followup.send(
                    f"I could not timeout that member: `{error}`", ephemeral=True
                )
                return
            await finish_safety_review(
                message,
                moderator,
                f"Timed out for {minutes} minutes",
                discord.Color.orange(),
            )
            await send_safety_log(
                interaction.guild,
                "⏳ Safety Review: Member Timed Out",
                f"{member.mention} (`{member.id}`) was timed out by {moderator.mention}.",
                color=discord.Color.orange(),
                fields=[
                    ("Detection", reason, False),
                    ("Duration", f"{minutes} minutes", True),
                    ("Ends", discord.utils.format_dt(until, style="F"), True),
                ],
            )
            await send_mod_log(
                interaction.guild,
                "server",
                "⏳ Member Timed Out from Safety Review",
                moderator,
                target=member,
                reason=reason,
                details=f"Duration: {minutes} minutes",
            )
        await interaction.followup.send(
            f"⏳ {member.mention} was timed out for {minutes} minutes.", ephemeral=True
        )

    @discord.ui.button(
        label="Ban",
        style=discord.ButtonStyle.danger,
        emoji="🔨",
        custom_id="harps:safety:review:ban",
    )
    async def ban_member(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await safety_review_context(interaction, "ban_members")
        if context is None:
            return
        message, metadata, moderator = context
        target_id = int(metadata["user_id"])
        member = interaction.guild.get_member(target_id)
        if member is not None:
            blocked = safety_target_block_reason(interaction.guild, moderator, member)
            if blocked:
                await interaction.response.send_message(blocked, ephemeral=True)
                return
        await interaction.response.send_message(
            f"Are you sure you want to ban <@{target_id}> (`{target_id}`)?",
            view=SafetyBanConfirmationView(
                message, target_id, moderator.id, str(metadata["reason"])
            ),
            ephemeral=True,
        )


def lfg_metadata(message: discord.Message) -> dict[str, int] | None:
    if not message.embeds:
        return None
    footer = message.embeds[0].footer.text or ""
    match = re.fullmatch(
        r"harps-lfg:guild=(\d+);host=(\d+);capacity=(\d+);expires=(\d+)",
        footer,
    )
    if match is None:
        return None
    return {
        "guild_id": int(match.group(1)),
        "host_id": int(match.group(2)),
        "capacity": int(match.group(3)),
        "expires": int(match.group(4)),
    }


def lfg_embed_field(embed: discord.Embed, name: str) -> str | None:
    field = discord.utils.get(embed.fields, name=name)
    return field.value if field is not None else None


def set_lfg_embed_field(embed: discord.Embed, name: str, value: str) -> None:
    for index, field in enumerate(embed.fields):
        if field.name == name:
            embed.set_field_at(index, name=name, value=value, inline=field.inline)
            return
    embed.add_field(name=name, value=value, inline=False)


def lfg_player_ids(embed: discord.Embed) -> list[int]:
    value = lfg_embed_field(embed, "Players") or ""
    return [int(item) for item in re.findall(r"<@(\d+)>", value)]


def lfg_status(embed: discord.Embed) -> str:
    return lfg_embed_field(embed, "Status") or "Unknown"


async def find_active_lfg_for_host(
    channel: discord.TextChannel, host_id: int
) -> discord.Message | None:
    async for message in channel.history(limit=200):
        metadata = lfg_metadata(message)
        if metadata is None or metadata["host_id"] != host_id or not message.embeds:
            continue
        if lfg_status(message.embeds[0]) in {"🟢 Open", "🔴 Full"}:
            return message
    return None


class LFGChoiceSelect(discord.ui.Select):
    def __init__(
        self,
        session: dict[str, str | int],
        key: str,
        placeholder: str,
        options: list[discord.SelectOption],
        row: int,
    ):
        self.session = session
        self.key = key
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.session[self.key] = self.values[0]
        await interaction.response.defer()


class LFGSetupView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=180)
        self.member_id = member.id
        self.session: dict[str, str | int] = {"host_id": member.id}
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "game",
                "1. Choose a game",
                [
                    discord.SelectOption(label=label, value=value, emoji="🎮")
                    for value, label in LFG_GAMES.items()
                ],
                0,
            )
        )
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "capacity",
                "2. Choose a team size",
                [
                    discord.SelectOption(
                        label=label,
                        value=value,
                        description=f"Up to {value} players",
                    )
                    for value, label in LFG_TEAM_SIZES.items()
                ],
                1,
            )
        )
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "region",
                "3. Choose your region",
                [
                    discord.SelectOption(label=label, value=value, emoji="🌍")
                    for value, label in LFG_REGIONS.items()
                ],
                2,
            )
        )
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "platform",
                "4. Choose your platform",
                [
                    discord.SelectOption(label=label, value=value, emoji="🕹️")
                    for value, label in LFG_PLATFORMS.items()
                ],
                3,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member_id:
            await interaction.response.send_message(
                "This LFG setup belongs to another member.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Continue",
        style=discord.ButtonStyle.primary,
        emoji="➡️",
        row=4,
    )
    async def continue_setup(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        missing = [
            key for key in ("game", "capacity", "region", "platform")
            if key not in self.session
        ]
        if missing:
            await interaction.response.send_message(
                "Choose a game, team size, region and platform first.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content="Almost done — choose your language and microphone preference.",
            view=LFGDetailsView(self.member_id, self.session),
        )


class LFGDetailsView(discord.ui.View):
    def __init__(self, member_id: int, session: dict[str, str | int]):
        super().__init__(timeout=180)
        self.member_id = member_id
        self.session = session
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "language",
                "5. Choose your language",
                [
                    discord.SelectOption(label="Greek", value="Greek", emoji="🇬🇷"),
                    discord.SelectOption(label="English", value="English", emoji="🇬🇧"),
                    discord.SelectOption(label="Greek & English", value="Greek & English", emoji="🌐"),
                ],
                0,
            )
        )
        self.add_item(
            LFGChoiceSelect(
                self.session,
                "microphone",
                "6. Is a microphone required?",
                [
                    discord.SelectOption(label="Required", value="Required", emoji="🎙️"),
                    discord.SelectOption(label="Optional", value="Optional", emoji="🔈"),
                    discord.SelectOption(label="Not required", value="Not required", emoji="🔇"),
                ],
                1,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member_id:
            await interaction.response.send_message(
                "This LFG setup belongs to another member.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Add Details & Publish",
        style=discord.ButtonStyle.success,
        emoji="📝",
        row=2,
    )
    async def open_details(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if "language" not in self.session or "microphone" not in self.session:
            await interaction.response.send_message(
                "Choose your language and microphone preference first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(LFGDetailsModal(self.session))


class LFGDetailsModal(discord.ui.Modal, title="Finish Your LFG Listing"):
    def __init__(self, session: dict[str, str | int]):
        super().__init__(timeout=300)
        self.session = session.copy()
        self.rank = discord.ui.TextInput(
            label="Rank / skill level",
            placeholder="Example: Gold, experienced, or any rank",
            default="Any rank / skill level",
            max_length=100,
            required=False,
        )
        self.play_time = discord.ui.TextInput(
            label="When are you playing?",
            placeholder="Example: Now, tonight at 20:00, or weekends",
            max_length=100,
        )
        self.requirements = discord.ui.TextInput(
            label="Requirements and details",
            placeholder="Describe the team, age preference, play style, goals, etc.",
            style=discord.TextStyle.paragraph,
            max_length=700,
        )
        self.add_item(self.rank)
        self.add_item(self.play_time)
        self.add_item(self.requirements)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        user_text = "\n".join(
            (str(self.rank), str(self.play_time), str(self.requirements))
        )
        if LINK_PATTERN.search(user_text):
            await interaction.response.send_message(
                "Links and Discord invites are not allowed in LFG listings.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await create_lfg_listing(
            interaction,
            self.session,
            rank=str(self.rank).strip() or "Any rank / skill level",
            play_time=str(self.play_time).strip(),
            requirements=str(self.requirements).strip(),
        )


class LFGCreatePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create LFG",
        style=discord.ButtonStyle.primary,
        emoji="🎮",
        custom_id="harps:lfg:create",
    )
    async def create_lfg(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "LFG listings can only be created inside the server.", ephemeral=True
            )
            return
        active_channel = await get_lfg_channel(
            interaction.guild, "active", create_if_missing=False
        )
        if isinstance(active_channel, discord.TextChannel):
            existing = await find_active_lfg_for_host(
                active_channel, interaction.user.id
            )
            if existing is not None:
                await interaction.response.send_message(
                    f"You already have an active LFG listing: {existing.jump_url}",
                    ephemeral=True,
                )
                return
        await interaction.response.send_message(
            "Build your team by completing each selection below.",
            view=LFGSetupView(interaction.user),
            ephemeral=True,
        )


async def create_lfg_listing(
    interaction: discord.Interaction,
    session: dict[str, str | int],
    *,
    rank: str,
    play_time: str,
    requirements: str,
) -> None:
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send(
            "LFG listings can only be created inside the server.", ephemeral=True
        )
        return
    if int(session.get("host_id", 0)) != interaction.user.id:
        await interaction.followup.send("This LFG setup is not yours.", ephemeral=True)
        return

    lock_key = (guild.id, interaction.user.id)
    lock = lfg_creation_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        try:
            channels = await ensure_lfg_hub(guild)
            active_channel = channels["active"]
            if not isinstance(active_channel, discord.TextChannel):
                raise RuntimeError("The active LFG channel is unavailable.")
            existing = await find_active_lfg_for_host(
                active_channel, interaction.user.id
            )
            if existing is not None:
                await interaction.followup.send(
                    f"You already have an active LFG listing: {existing.jump_url}",
                    ephemeral=True,
                )
                return

            game_key = str(session["game"])
            region_key = str(session["region"])
            platform_key = str(session["platform"])
            capacity_key = str(session["capacity"])
            capacity = int(capacity_key)
            expires_at = discord.utils.utcnow() + timedelta(hours=LFG_EXPIRY_HOURS)
            embed = discord.Embed(
                title=f"🎮 {LFG_GAMES[game_key]} • {LFG_TEAM_SIZES[capacity_key]}",
                description=(
                    f"{interaction.user.mention} is building a team. Use the buttons "
                    "below to join, leave, contact the host, or close the listing."
                ),
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Game", value=LFG_GAMES[game_key], inline=True)
            embed.add_field(name="Team", value=LFG_TEAM_SIZES[capacity_key], inline=True)
            embed.add_field(name="Region", value=LFG_REGIONS[region_key], inline=True)
            embed.add_field(name="Platform", value=LFG_PLATFORMS[platform_key], inline=True)
            embed.add_field(name="Language", value=str(session["language"]), inline=True)
            embed.add_field(name="Microphone", value=str(session["microphone"]), inline=True)
            embed.add_field(name="Rank / skill", value=shortened(rank, 100), inline=False)
            embed.add_field(name="Playing", value=shortened(play_time, 100), inline=False)
            embed.add_field(
                name="Requirements", value=shortened(requirements, 700), inline=False
            )
            embed.add_field(name="Players", value=interaction.user.mention, inline=False)
            embed.add_field(name="Team progress", value=f"**1 / {capacity}**", inline=True)
            embed.add_field(name="Status", value="🟢 Open", inline=True)
            embed.add_field(
                name="Expires",
                value=discord.utils.format_dt(expires_at, style="R"),
                inline=True,
            )
            if guild.icon is not None:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(
                text=(
                    f"harps-lfg:guild={guild.id};host={interaction.user.id};"
                    f"capacity={capacity};expires={int(expires_at.timestamp())}"
                )
            )
            listing = await active_channel.send(
                embed=embed,
                view=LFGListingView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException, KeyError, RuntimeError) as error:
            await interaction.followup.send(
                f"I could not publish the LFG listing: `{error}`", ephemeral=True
            )
            return
        finally:
            lfg_creation_locks.pop(lock_key, None)

    await send_lfg_log(
        guild,
        "🎮 LFG Listing Created",
        f"{interaction.user.mention} created a new listing in {active_channel.mention}.",
        color=discord.Color.green(),
        fields=[
            ("Game", LFG_GAMES[game_key], True),
            ("Team", LFG_TEAM_SIZES[capacity_key], True),
            ("Listing", listing.jump_url, False),
        ],
    )
    await interaction.followup.send(
        f"✅ Your LFG listing is live: {listing.jump_url}", ephemeral=True
    )


async def lfg_listing_context(
    interaction: discord.Interaction,
) -> tuple[discord.Message, dict[str, int], discord.Member] | None:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This LFG button can only be used inside the server.", ephemeral=True
        )
        return None
    if interaction.message is None:
        await interaction.response.send_message(
            "I could not find this LFG listing.", ephemeral=True
        )
        return None
    try:
        message = await interaction.channel.fetch_message(interaction.message.id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        message = interaction.message
    metadata = lfg_metadata(message)
    if metadata is None or metadata["guild_id"] != interaction.guild.id:
        await interaction.response.send_message(
            "This is not a valid Harps Community LFG listing.", ephemeral=True
        )
        return None
    return message, metadata, interaction.user


async def update_lfg_players(
    message: discord.Message,
    embed: discord.Embed,
    metadata: dict[str, int],
    player_ids: list[int],
) -> None:
    player_text = "\n".join(f"<@{member_id}>" for member_id in player_ids)
    set_lfg_embed_field(embed, "Players", player_text)
    set_lfg_embed_field(
        embed,
        "Team progress",
        f"**{len(player_ids)} / {metadata['capacity']}**",
    )
    full = len(player_ids) >= metadata["capacity"]
    set_lfg_embed_field(embed, "Status", "🔴 Full" if full else "🟢 Open")
    embed.color = discord.Color.red() if full else discord.Color.blurple()
    await message.edit(
        embed=embed,
        view=LFGListingView(join_disabled=full),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def archive_lfg_listing(
    message: discord.Message,
    status: str,
    *,
    actor: discord.Member | None = None,
) -> None:
    metadata = lfg_metadata(message)
    if metadata is None or not message.embeds or message.guild is None:
        return
    embed = discord.Embed.from_dict(message.embeds[0].to_dict())
    set_lfg_embed_field(embed, "Status", status)
    embed.color = discord.Color.dark_grey()
    if actor is not None:
        embed.add_field(
            name="Closed by", value=f"{actor.mention} (`{actor.id}`)", inline=False
        )
    try:
        await message.edit(
            embed=embed,
            view=LFGListingView(disabled=True),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

    completed_channel = await get_lfg_channel(message.guild, "completed")
    if isinstance(completed_channel, discord.TextChannel):
        await completed_channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    try:
        await message.delete(reason=f"LFG listing archived: {status}")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass
    await send_lfg_log(
        message.guild,
        "✅ LFG Listing Archived",
        f"Listing `{message.id}` was archived with status **{status}**.",
        color=discord.Color.dark_grey(),
        fields=[
            ("Host", f"<@{metadata['host_id']}> (`{metadata['host_id']}`)", True),
            (
                "Action by",
                f"{actor.mention} (`{actor.id}`)" if actor else "Automatic expiry",
                True,
            ),
        ],
    )


class LFGListingView(discord.ui.View):
    def __init__(self, *, join_disabled: bool = False, disabled: bool = False):
        super().__init__(timeout=None)
        for item in self.children:
            if disabled or (item.custom_id == "harps:lfg:join" and join_disabled):
                item.disabled = True

    @discord.ui.button(
        label="Join Team",
        style=discord.ButtonStyle.success,
        emoji="➕",
        custom_id="harps:lfg:join",
    )
    async def join_team(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await lfg_listing_context(interaction)
        if context is None:
            return
        message, metadata, member = context
        await interaction.response.defer(ephemeral=True)
        lock = lfg_listing_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            try:
                message = await interaction.channel.fetch_message(message.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.followup.send(
                    "That listing is no longer available.", ephemeral=True
                )
                return
            if metadata["expires"] <= int(discord.utils.utcnow().timestamp()):
                await archive_lfg_listing(message, "⌛ Expired")
                await interaction.followup.send(
                    "That listing has expired.", ephemeral=True
                )
                return
            embed = discord.Embed.from_dict(message.embeds[0].to_dict())
            players = lfg_player_ids(embed)
            if member.id in players:
                await interaction.followup.send(
                    "You are already in this team.", ephemeral=True
                )
                return
            if len(players) >= metadata["capacity"]:
                await interaction.followup.send("That team is full.", ephemeral=True)
                return
            players.append(member.id)
            await update_lfg_players(message, embed, metadata, players)

        host = interaction.guild.get_member(metadata["host_id"])
        if host is not None:
            try:
                await host.send(
                    f"➕ **{member}** joined your LFG team in **{interaction.guild.name}**.\n"
                    f"Listing: {message.jump_url}"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_lfg_log(
            interaction.guild,
            "➕ Member Joined LFG",
            f"{member.mention} joined <@{metadata['host_id']}>'s LFG team.",
            color=discord.Color.green(),
            fields=[("Listing", message.jump_url, False)],
        )
        await interaction.followup.send(
            "✅ You joined the team. The host has been notified.", ephemeral=True
        )

    @discord.ui.button(
        label="Leave Team",
        style=discord.ButtonStyle.secondary,
        emoji="➖",
        custom_id="harps:lfg:leave",
    )
    async def leave_team(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await lfg_listing_context(interaction)
        if context is None:
            return
        message, metadata, member = context
        if member.id == metadata["host_id"]:
            await interaction.response.send_message(
                "The host cannot leave their own listing. Use Close LFG instead.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = lfg_listing_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            try:
                message = await interaction.channel.fetch_message(message.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.followup.send(
                    "That listing is no longer available.", ephemeral=True
                )
                return
            embed = discord.Embed.from_dict(message.embeds[0].to_dict())
            players = lfg_player_ids(embed)
            if member.id not in players:
                await interaction.followup.send(
                    "You are not currently in this team.", ephemeral=True
                )
                return
            players.remove(member.id)
            await update_lfg_players(message, embed, metadata, players)
        await send_lfg_log(
            interaction.guild,
            "➖ Member Left LFG",
            f"{member.mention} left <@{metadata['host_id']}>'s LFG team.",
            color=discord.Color.orange(),
            fields=[("Listing", message.jump_url, False)],
        )
        await interaction.followup.send("You left the team.", ephemeral=True)

    @discord.ui.button(
        label="Contact Host",
        style=discord.ButtonStyle.primary,
        emoji="💬",
        custom_id="harps:lfg:contact",
    )
    async def contact_host(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await lfg_listing_context(interaction)
        if context is None:
            return
        message, metadata, member = context
        host = interaction.guild.get_member(metadata["host_id"])
        if host is None:
            await interaction.response.send_message(
                "The host is no longer in the server.", ephemeral=True
            )
            return
        if host.id == member.id:
            await interaction.response.send_message(
                "You are the host of this listing.", ephemeral=True
            )
            return
        try:
            await host.send(
                f"💬 **{member}** wants to contact you about your LFG listing in "
                f"**{interaction.guild.name}**.\nListing: {message.jump_url}"
            )
            result = "✅ The host was notified by DM. You can also open their profile from the mention below."
        except (discord.Forbidden, discord.HTTPException):
            result = "The host's DMs are closed. Open their profile from the mention below."
        await interaction.response.send_message(
            f"{result}\nHost: {host.mention}", ephemeral=True
        )

    @discord.ui.button(
        label="Close LFG",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="harps:lfg:close",
    )
    async def close_lfg(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        context = await lfg_listing_context(interaction)
        if context is None:
            return
        message, metadata, member = context
        if member.id != metadata["host_id"] and not is_staff(member):
            await interaction.response.send_message(
                "Only the host or authorized staff can close this listing.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = lfg_listing_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            await archive_lfg_listing(message, "✅ Closed", actor=member)
        await interaction.followup.send("✅ The LFG listing was closed.", ephemeral=True)


# Register persistent views before connecting so their buttons survive restarts.
bot.add_view(TicketPanelView())
bot.add_view(CloseTicketView())
bot.add_view(RoleRequestPanelView())
bot.add_view(RoleRequestDecisionView())
bot.add_view(BoostPanelView())
bot.add_view(SafetyReviewView())
bot.add_view(LFGCreatePanelView())
bot.add_view(LFGListingView())


async def remove_unsafe_message(message: discord.Message) -> bool:
    try:
        await message.delete(reason="Harps Community chat safety filter")
        return True
    except discord.NotFound:
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not remove unsafe message {message.id}: {error}")
        return False


async def immediately_ban_for_safety(
    message: discord.Message, reason_code: str, reason_name: str
) -> None:
    """Ban a non-whitelisted link/everyone sender and purge seven days of messages."""
    message_removed = await remove_unsafe_message(message)
    preview = shortened(message.content or "[empty message]", 1000)
    guild = message.guild
    member = message.author

    blocked = (
        "The bot member was not available."
        if guild.me is None
        else safety_target_block_reason(guild, guild.me, member)
    )
    if blocked:
        await send_safety_review(
            message,
            reason_code,
            f"{reason_name} (automatic ban failed)",
            f"**Message**\n{preview}\n\n**Failure**\n{blocked}",
        )
        await send_safety_log(
            guild,
            "⚠️ Immediate Safety Ban Failed",
            f"The violating message from {member.mention} was sent to staff review.",
            color=discord.Color.orange(),
            fields=[
                ("Reason", reason_name, False),
                ("Failure", blocked, False),
                ("Message removed", "Yes" if message_removed else "No", True),
            ],
        )
        return

    try:
        await guild.ban(
            member,
            reason=f"Immediate chat safety ban: {reason_name}",
            delete_message_seconds=SAFETY_BAN_DELETE_SECONDS,
        )
    except (discord.Forbidden, discord.HTTPException) as error:
        await send_safety_review(
            message,
            reason_code,
            f"{reason_name} (automatic ban failed)",
            f"**Message**\n{preview}\n\n**Failure**\n{error}",
        )
        await send_safety_log(
            guild,
            "⚠️ Immediate Safety Ban Failed",
            f"The violating message from {member.mention} was sent to staff review.",
            color=discord.Color.orange(),
            fields=[
                ("Reason", reason_name, False),
                ("Failure", str(error), False),
                ("Message removed", "Yes" if message_removed else "No", True),
            ],
        )
        return

    safety_message_activity.pop((guild.id, member.id), None)
    safety_duplicate_activity.pop((guild.id, member.id), None)
    await send_safety_log(
        guild,
        "🔨 Immediate Chat Safety Ban",
        (
            f"{member.mention} (`{member.id}`) was banned immediately and up to "
            "seven days of their recent server messages were deleted."
        ),
        color=discord.Color.red(),
        fields=[
            ("Reason", reason_name, False),
            ("Message", preview, False),
            ("Trigger message removed", "Yes" if message_removed else "No", True),
        ],
    )
    await send_mod_log(
        guild,
        "ban",
        "🔨 Immediate Chat Safety Ban",
        guild.me,
        target=member,
        reason=reason_name,
        details="Discord ban cleanup requested for the previous seven days of messages",
        color=discord.Color.red(),
    )


async def automatically_timeout_for_safety(
    member: discord.Member, reason_name: str, minutes: int
) -> tuple[bool, str, datetime]:
    guild = member.guild
    if guild.me is None:
        return False, "The bot member was not available.", discord.utils.utcnow()
    if not guild.me.guild_permissions.moderate_members:
        return False, "The bot needs the Moderate Members permission.", discord.utils.utcnow()
    blocked = safety_target_block_reason(guild, guild.me, member)
    if blocked:
        return False, blocked, discord.utils.utcnow()
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    try:
        await member.timeout(
            until,
            reason=f"Automatic chat safety action: {reason_name}",
        )
    except (discord.Forbidden, discord.HTTPException) as error:
        return False, str(error), until
    try:
        await member.send(
            f"⏳ You were automatically timed out for **{minutes} minutes** in "
            f"**{guild.name}**.\nReason: {reason_name}\n"
            "If you believe this was a mistake, please contact the staff team."
        )
    except (discord.Forbidden, discord.HTTPException):
        pass
    return True, "Timeout applied", until


async def handle_safety_incident(
    message: discord.Message,
    reason_code: str,
    reason_name: str,
    evidence: str,
    *,
    automatic: bool,
    config: dict[str, int],
) -> None:
    message_removed = await remove_unsafe_message(message)
    now = time.monotonic()
    cooldown_key = (message.guild.id, message.author.id, reason_code)
    last_incident = safety_incident_cooldowns.get(cooldown_key, 0.0)
    if now - last_incident < SAFETY_INCIDENT_COOLDOWN_SECONDS:
        return
    safety_incident_cooldowns[cooldown_key] = now

    common_fields = [
        ("Member", f"{message.author.mention}\n`{message.author.id}`", True),
        ("Channel", f"{message.channel.mention}\n`{message.channel.id}`", True),
        ("Detection", reason_name, False),
        ("Evidence", shortened(evidence, 1024), False),
        ("Message removed", "Yes" if message_removed else "No", True),
    ]
    if automatic:
        success, result, until = await automatically_timeout_for_safety(
            message.author, reason_name, config["timeout_minutes"]
        )
        if success:
            await send_safety_log(
                message.guild,
                "🚨 Automatic Chat Safety Action",
                (
                    f"{message.author.mention} was automatically timed out for "
                    f"**{config['timeout_minutes']} minutes** after clearly repeated abuse."
                ),
                color=discord.Color.red(),
                fields=common_fields
                + [("Timeout ends", discord.utils.format_dt(until, style="F"), False)],
            )
            await send_mod_log(
                message.guild,
                "server",
                "🚨 Automatic Safety Timeout",
                message.guild.me,
                target=message.author,
                reason=reason_name,
                details=f"Duration: {config['timeout_minutes']} minutes",
                color=discord.Color.red(),
            )
            return

        review_evidence = f"{evidence}\n\nAutomatic timeout failed: {result}"
        await send_safety_review(
            message, reason_code, f"{reason_name} (automatic action failed)", review_evidence
        )
        await send_safety_log(
            message.guild,
            "⚠️ Automatic Safety Action Failed",
            "The incident was moved to staff review because the timeout could not be applied.",
            color=discord.Color.orange(),
            fields=common_fields + [("Failure", result, False)],
        )
        return

    review_created = await send_safety_review(
        message, reason_code, reason_name, evidence
    )
    await send_safety_log(
        message.guild,
        "🔎 Chat Safety Incident Queued",
        (
            "The suspicious message was removed and queued for staff review. "
            "No member punishment was applied."
        ),
        color=discord.Color.gold(),
        fields=common_fields
        + [("Review created", "Yes" if review_created else "No", True)],
    )


async def inspect_message_for_safety(message: discord.Message) -> None:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return
    if is_safety_whitelisted(message.author) or is_safety_exempt_channel(message.channel):
        return

    if LINK_PATTERN.search(message.content):
        await immediately_ban_for_safety(
            message, "forbidden_link", "Posted a link without safety whitelist"
        )
        return
    if message.mention_everyone:
        await immediately_ban_for_safety(
            message,
            "everyone_mention",
            "Used @everyone/@here without safety whitelist",
        )
        return

    now = time.monotonic()
    member_key = (message.guild.id, message.author.id)
    review_channel = await get_safety_channel(
        message.guild, "review", create_if_missing=False
    )
    config = safety_config_from_channel(review_channel)

    message_times = safety_message_activity[member_key]
    message_times.append(now)
    message_count = prune_safety_timestamps(
        message_times, now, SAFETY_SPAM_WINDOW_SECONDS
    )

    normalized = re.sub(r"\s+", " ", message.content).strip().casefold()
    recent_content = safety_duplicate_activity[member_key]
    while recent_content and now - recent_content[0][0] > SAFETY_DUPLICATE_WINDOW_SECONDS:
        recent_content.popleft()
    if normalized:
        recent_content.append((now, normalized))
    duplicate_count = (
        sum(1 for _, content in recent_content if content == normalized)
        if len(normalized) >= 5
        else 0
    )

    user_mentions = len(re.findall(r"<@!?\d+>", message.content))
    role_mentions = len(re.findall(r"<@&\d+>", message.content))
    mention_count = user_mentions + role_mentions

    preview_parts = [message.content or "[empty message]"]
    if message.attachments:
        preview_parts.append(
            "Attachments: " + ", ".join(item.filename for item in message.attachments)
        )
    preview = shortened("\n".join(preview_parts), 700)
    metrics = (
        f"Messages: {message_count}/{SAFETY_SPAM_WINDOW_SECONDS}s | "
        f"Duplicates: {duplicate_count}/{SAFETY_DUPLICATE_WINDOW_SECONDS}s | "
        f"User/role mentions: {mention_count}"
    )
    evidence = f"**Message**\n{preview}\n\n**Detection totals**\n{metrics}"

    if mention_count >= config["mention_auto"]:
        await handle_safety_incident(
            message,
            "mass_mentions",
            "Mass user/role mentions",
            evidence,
            automatic=True,
            config=config,
        )
    elif duplicate_count >= config["duplicate_auto"]:
        await handle_safety_incident(
            message,
            "duplicate_message_flood",
            "Repeated duplicate-message flood",
            evidence,
            automatic=True,
            config=config,
        )
    elif message_count >= config["spam_auto"]:
        await handle_safety_incident(
            message,
            "message_flood",
            "High-speed message flood",
            evidence,
            automatic=True,
            config=config,
        )
    elif mention_count >= config["mention_review"]:
        await handle_safety_incident(
            message,
            "excessive_mentions",
            "Excessive user/role mentions",
            evidence,
            automatic=False,
            config=config,
        )
    elif duplicate_count >= config["duplicate_review"]:
        await handle_safety_incident(
            message,
            "duplicate_messages",
            "Repeated duplicate messages",
            evidence,
            automatic=False,
            config=config,
        )
    elif message_count >= config["spam_review"]:
        await handle_safety_incident(
            message,
            "rapid_messaging",
            "Rapid messaging",
            evidence,
            automatic=False,
            config=config,
        )


@tasks.loop(minutes=15)
async def lfg_expiry_task() -> None:
    now_timestamp = int(discord.utils.utcnow().timestamp())
    for guild in bot.guilds:
        channel = await get_lfg_channel(guild, "active", create_if_missing=False)
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            async for message in channel.history(limit=200):
                metadata = lfg_metadata(message)
                if metadata is None or metadata["expires"] > now_timestamp:
                    continue
                lock = lfg_listing_locks.setdefault(message.id, asyncio.Lock())
                async with lock:
                    await archive_lfg_listing(message, "⌛ Expired")
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not expire LFG listings in {guild.name}: {error}")


@lfg_expiry_task.before_loop
async def before_lfg_expiry_task() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    global slash_commands_synced
    print(f"✅ Logged in as {bot.user}")
    if not lfg_expiry_task.is_running():
        lfg_expiry_task.start()
    if not slash_commands_synced:
        try:
            guild_command_count = 0
            for guild in bot.guilds:
                bot.tree.copy_global_to(guild=guild)
                guild_commands = await bot.tree.sync(guild=guild)
                guild_command_count += len(guild_commands)
            synced_commands = await bot.tree.sync()
        except Exception as error:
            print(f"Could not sync slash commands: {error}")
        else:
            slash_commands_synced = True
            print(
                f"✅ Synced {len(synced_commands)} global slash commands and "
                f"{guild_command_count} instant server commands"
            )
    for guild in bot.guilds:
        try:
            await ensure_server_logging(guild)
            await ensure_antinuke_whitelist_role(guild)
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not initialize server logs/anti-nuke in {guild.name}: {error}")
        try:
            await ensure_safety_center(guild)
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not initialize chat safety in {guild.name}: {error}")
        try:
            await update_member_count(guild)
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not update member counter in {guild.name}: {error}")
        try:
            updated, failed = await sync_regular_roles(
                guild, "Harps Community automatic startup autorole sync"
            )
            if updated or failed:
                print(
                    f"Autorole sync in {guild.name}: {updated} updated, {failed} failed"
                )
        except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
            print(f"Could not sync {AUTO_ROLE_NAME} in {guild.name}: {error}")


@bot.event
async def on_member_join(member: discord.Member):
    await send_server_log(
        member.guild,
        "member",
        "📥 Member Joined",
        f"{member.mention} (`{member.id}`) joined the server.",
        color=discord.Color.green(),
        fields=[
            ("Account created", discord.utils.format_dt(member.created_at, style="F"), False),
            ("Bot", "Yes" if member.bot else "No", True),
            ("Member count", str(member.guild.member_count or len(member.guild.members)), True),
        ],
    )
    if member.bot and await handle_unauthorized_bot_add(member):
        try:
            await update_member_count(member.guild)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return
    try:
        await give_regular_role(member)
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
        print(f"Could not give {AUTO_ROLE_NAME} to {member}: {error}")
    await send_welcome(member)
    try:
        await update_member_count(member.guild)
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not update member counter in {member.guild.name}: {error}")
    if member.guild.me is not None:
        await send_mod_log(
            member.guild,
            "server",
            "📥 Member Joined",
            member.guild.me,
            target=member,
            reason="Member joined the server",
            color=discord.Color.green(),
        )


@bot.event
async def on_member_remove(member: discord.Member):
    await send_server_log(
        member.guild,
        "member",
        "📤 Member Left",
        f"{member.mention} (`{member.id}`) left or was removed from the server.",
        color=discord.Color.red(),
        fields=[
            ("Username", str(member), True),
            ("Bot", "Yes" if member.bot else "No", True),
            ("Joined", discord.utils.format_dt(member.joined_at, style="F") if member.joined_at else "Unknown", False),
        ],
    )
    await check_recent_member_removals(member.guild, member.id)
    await send_goodbye(member)
    try:
        await update_member_count(member.guild)
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"Could not update member counter in {member.guild.name}: {error}")
    if member.guild.me is not None:
        await send_mod_log(
            member.guild,
            "server",
            "📤 Member Left",
            member.guild.me,
            target=member,
            reason="Member left or was removed from the server",
            color=discord.Color.red(),
        )


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User | discord.Member):
    entry = await find_recent_audit_entry(
        guild, discord.AuditLogAction.ban, target_id=user.id
    )
    actor = entry.user if entry else None
    await send_server_log(
        guild,
        "member",
        "🔨 Member Banned",
        f"{user.mention} (`{user.id}`) was banned.",
        color=discord.Color.red(),
        fields=[
            ("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False),
            ("Reason", entry.reason if entry and entry.reason else "No reason provided", False),
        ],
    )
    if actor is not None:
        await check_mass_action(
            guild,
            actor,
            "member_ban",
            "Mass member bans",
            f"Banned {user} ({user.id})",
        )


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    antinuke_triggered.discard((guild.id, user.id))
    entry = await find_recent_audit_entry(
        guild, discord.AuditLogAction.unban, target_id=user.id, attempts=2
    )
    actor = entry.user if entry else None
    await send_server_log(
        guild,
        "member",
        "✅ Member Unbanned",
        f"{user.mention} (`{user.id}`) was unbanned.",
        color=discord.Color.green(),
        fields=[
            ("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False),
            ("Reason", entry.reason if entry and entry.reason else "No reason provided", False),
        ],
    )


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    entry = await find_recent_audit_entry(
        channel.guild,
        discord.AuditLogAction.channel_create,
        target_id=channel.id,
        attempts=2,
    )
    actor = entry.user if entry else None
    await send_server_log(
        channel.guild,
        "channel",
        "➕ Channel Created",
        f"**{channel.name}** (`{channel.id}`) was created.",
        color=discord.Color.green(),
        fields=[("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False)],
    )


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    entry = await find_recent_audit_entry(
        channel.guild, discord.AuditLogAction.channel_delete, target_id=channel.id
    )
    actor = entry.user if entry else None
    await send_server_log(
        channel.guild,
        "channel",
        "➖ Channel Deleted",
        f"**{channel.name}** (`{channel.id}`) was deleted.",
        color=discord.Color.red(),
        fields=[("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False)],
    )
    if actor is not None:
        await punish_nuke_actor(
            channel.guild,
            actor,
            "Channel deletion",
            f"Deleted {channel.name} ({channel.id})",
        )
    else:
        await send_server_log(
            channel.guild,
            "antinuke",
            "⚠️ Channel Deletion Actor Unknown",
            f"Could not identify who deleted **{channel.name}** (`{channel.id}`); no automatic ban was attempted.",
            color=discord.Color.orange(),
        )


@bot.event
async def on_guild_channel_update(
    before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
):
    # The bot renames this statistics channel whenever the member total
    # changes. That internal update is expected and should not create noise.
    if before.name.startswith(MEMBER_COUNT_CHANNEL_PREFIX) or after.name.startswith(
        MEMBER_COUNT_CHANNEL_PREFIX
    ):
        return

    changes = []
    if before.name != after.name:
        changes.append(f"Name: `{before.name}` → `{after.name}`")
    if before.category_id != after.category_id:
        changes.append(f"Category ID: `{before.category_id}` → `{after.category_id}`")
    if not changes:
        return
    entry = await find_recent_audit_entry(
        after.guild,
        discord.AuditLogAction.channel_update,
        target_id=after.id,
        attempts=1,
    )
    actor = entry.user if entry else None
    await send_server_log(
        after.guild,
        "channel",
        "✏️ Channel Updated",
        f"{after.mention} (`{after.id}`) was updated.",
        fields=[
            ("Changes", "\n".join(changes), False),
            ("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False),
        ],
    )


@bot.event
async def on_guild_role_create(role: discord.Role):
    entry = await find_recent_audit_entry(
        role.guild, discord.AuditLogAction.role_create, target_id=role.id
    )
    actor = entry.user if entry else None
    await send_server_log(
        role.guild,
        "role",
        "➕ Role Created",
        f"**{role.name}** (`{role.id}`) was created.",
        color=discord.Color.green(),
        fields=[("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False)],
    )
    if actor is not None:
        await check_mass_action(
            role.guild,
            actor,
            "role_structure",
            "Mass role creation/deletion",
            f"Created role {role.name} ({role.id})",
        )


@bot.event
async def on_guild_role_delete(role: discord.Role):
    entry = await find_recent_audit_entry(
        role.guild, discord.AuditLogAction.role_delete, target_id=role.id
    )
    actor = entry.user if entry else None
    await send_server_log(
        role.guild,
        "role",
        "➖ Role Deleted",
        f"**{role.name}** (`{role.id}`) was deleted.",
        color=discord.Color.red(),
        fields=[("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False)],
    )
    if actor is not None:
        await check_mass_action(
            role.guild,
            actor,
            "role_structure",
            "Mass role creation/deletion",
            f"Deleted role {role.name} ({role.id})",
        )


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    changes = []
    if before.name != after.name:
        changes.append(f"Name: `{before.name}` → `{after.name}`")
    if before.permissions != after.permissions:
        changes.append("Role permissions changed")
    if before.color != after.color:
        changes.append(f"Color: `{before.color}` → `{after.color}`")
    if not changes:
        return
    entry = await find_recent_audit_entry(
        after.guild,
        discord.AuditLogAction.role_update,
        target_id=after.id,
        attempts=1,
    )
    actor = entry.user if entry else None
    await send_server_log(
        after.guild,
        "role",
        "✏️ Role Updated",
        f"**{after.name}** (`{after.id}`) was updated.",
        fields=[
            ("Changes", "\n".join(changes), False),
            ("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False),
        ],
    )


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    before_role_ids = {role.id for role in before.roles}
    after_role_ids = {role.id for role in after.roles}
    added_roles = [role for role in after.roles if role.id not in before_role_ids]
    removed_roles = [role for role in before.roles if role.id not in after_role_ids]

    if added_roles or removed_roles:
        changes = []
        if added_roles:
            changes.append("Added: " + ", ".join(role.name for role in added_roles))
        if removed_roles:
            changes.append("Removed: " + ", ".join(role.name for role in removed_roles))
        entry = await find_recent_audit_entry(
            after.guild,
            discord.AuditLogAction.member_role_update,
            target_id=after.id,
        )
        actor = entry.user if entry else None
        await send_server_log(
            after.guild,
            "role",
            "👤 Member Roles Updated",
            f"Roles changed for {after.mention} (`{after.id}`).",
            fields=[
                ("Changes", "\n".join(changes), False),
                ("Action by", f"{actor.mention} (`{actor.id}`)" if actor else "Unknown", False),
            ],
        )
        # Role additions never trigger anti-nuke. Only removals count.
        if removed_roles and actor is not None:
            await check_mass_action(
                after.guild,
                actor,
                "member_role_remove",
                "Mass role removals from members",
                f"Removed {len(removed_roles)} role(s) from {after} ({after.id})",
                weight=len(removed_roles),
            )

    if before.display_name != after.display_name:
        await send_server_log(
            after.guild,
            "member",
            "✏️ Member Name Updated",
            f"{after.mention} (`{after.id}`) changed display name.",
            fields=[("Before", before.display_name, True), ("After", after.display_name, True)],
        )


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id)
    cached = payload.cached_message
    author = cached.author if cached else None
    content = cached.clean_content if cached else "Message was not cached; content unavailable."
    attachments = "\n".join(item.url for item in cached.attachments) if cached else "None"
    await send_server_log(
        guild,
        "message",
        "🗑️ Message Deleted",
        shortened(content, 3500),
        color=discord.Color.red(),
        fields=[
            ("Author", f"{author.mention} (`{author.id}`)" if author else "Unknown", False),
            ("Channel", channel.mention if channel else f"`{payload.channel_id}`", True),
            ("Message ID", str(payload.message_id), True),
            ("Attachments", attachments, False),
        ],
    )


@bot.event
async def on_raw_bulk_message_delete(payload: discord.RawBulkMessageDeleteEvent):
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id)
    await send_server_log(
        guild,
        "message",
        "🧹 Messages Bulk Deleted",
        f"**{len(payload.message_ids)}** messages were deleted.",
        color=discord.Color.red(),
        fields=[
            ("Channel", channel.mention if channel else f"`{payload.channel_id}`", True),
            ("Message IDs", shortened(", ".join(str(item) for item in payload.message_ids)), False),
        ],
    )


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    if payload.guild_id is None or "content" not in payload.data:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id)
    cached = payload.cached_message
    author_data = payload.data.get("author", {})
    author_id = author_data.get("id")
    is_bot_message = bool(author_data.get("bot")) or (
        cached is not None and cached.author.bot
    )
    if bot.user is not None and author_id == str(bot.user.id):
        is_bot_message = True
    if is_bot_message:
        return

    before_content = cached.clean_content if cached else "Message was not cached."
    raw_after_content = payload.data.get("content")
    # Discord can emit empty raw updates for embed/link-preview changes. They
    # are not actual user text edits and should not pollute message-logs.
    if cached is None and not raw_after_content:
        return
    after_content = raw_after_content or "[empty message]"
    if cached is not None and cached.content == after_content:
        return
    author_text = f"<@{author_id}> (`{author_id}`)" if author_id else "Unknown"
    await send_server_log(
        guild,
        "message",
        "✏️ Message Edited",
        f"A message was edited in {channel.mention if channel else f'`{payload.channel_id}`'}.",
        color=discord.Color.gold(),
        fields=[
            ("Author", author_text, False),
            ("Before", before_content, False),
            ("After", after_content, False),
            ("Message ID", str(payload.message_id), True),
        ],
    )


async def log_reaction_event(
    payload: discord.RawReactionActionEvent, action_name: str
) -> None:
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id)
    member = payload.member or guild.get_member(payload.user_id)
    user_text = f"{member.mention} (`{member.id}`)" if member else f"`{payload.user_id}`"
    message_link = (
        f"https://discord.com/channels/{guild.id}/{payload.channel_id}/{payload.message_id}"
    )
    await send_server_log(
        guild,
        "reaction",
        f"{action_name} Reaction",
        f"{user_text} {action_name.lower()} `{payload.emoji}`.",
        color=discord.Color.green() if action_name == "Added" else discord.Color.red(),
        fields=[
            ("Channel", channel.mention if channel else f"`{payload.channel_id}`", True),
            ("Message", f"[Open message]({message_link})", True),
        ],
    )


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await log_reaction_event(payload, "Added")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    await log_reaction_event(payload, "Removed")


async def handle_lfg_voice_state(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    guild = member.guild
    category = discord.utils.get(guild.categories, name=LFG_CATEGORY_NAME)
    if category is None:
        return

    if after.channel is not None and after.channel.name == LFG_VOICE_CREATOR_NAME:
        lock_key = (guild.id, member.id)
        lock = lfg_voice_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            existing = discord.utils.find(
                lambda channel: (
                    channel.name.startswith(LFG_TEMP_VOICE_PREFIX)
                    and channel.overwrites_for(member).priority_speaker is True
                ),
                category.voice_channels,
            )
            if existing is not None:
                try:
                    await member.move_to(
                        existing, reason="Returning member to their LFG voice room"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

            safe_name = re.sub(r"[^\w '\-]", "", member.display_name).strip()
            safe_name = safe_name[:70] or "Player"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    priority_speaker=True,
                ),
            }
            if guild.me is not None:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    move_members=True,
                    manage_channels=True,
                )
            try:
                room = await guild.create_voice_channel(
                    f"{LFG_TEMP_VOICE_PREFIX}{safe_name}'s Room"[:100],
                    category=category,
                    overwrites=overwrites,
                    user_limit=5,
                    reason=f"Temporary LFG voice room for {member} ({member.id})",
                )
                lfg_temp_voice_owners[room.id] = member.id
                await member.move_to(
                    room, reason="Moved member into their temporary LFG voice room"
                )
            except (discord.Forbidden, discord.HTTPException) as error:
                print(f"Could not create/move to LFG voice room in {guild.name}: {error}")
                if "room" in locals():
                    try:
                        await room.delete(reason="Could not move owner into LFG room")
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                return
            finally:
                lfg_voice_locks.pop(lock_key, None)

        await send_lfg_log(
            guild,
            "🔊 Temporary Voice Room Created",
            f"{member.mention} created {room.mention}.",
            color=discord.Color.green(),
        )

    if (
        before.channel is not None
        and before.channel.category_id == category.id
        and before.channel.name.startswith(LFG_TEMP_VOICE_PREFIX)
        and not before.channel.members
    ):
        channel_id = before.channel.id
        try:
            await before.channel.delete(reason="Empty temporary LFG voice room")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not delete empty LFG voice room in {guild.name}: {error}")
        else:
            owner_id = lfg_temp_voice_owners.pop(channel_id, None)
            await send_lfg_log(
                guild,
                "🔇 Temporary Voice Room Deleted",
                f"Empty room `{channel_id}` was deleted.",
                color=discord.Color.orange(),
                fields=[
                    ("Owner", f"<@{owner_id}>" if owner_id else "Unknown", True)
                ],
            )


@bot.event
async def on_voice_state_update(
    member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
):
    if before.channel == after.channel:
        return
    await handle_lfg_voice_state(member, before, after)
    if before.channel is None:
        action = f"joined {after.channel.mention}"
        title = "🔊 Voice Channel Joined"
        color = discord.Color.green()
    elif after.channel is None:
        action = f"left {before.channel.mention}"
        title = "🔇 Voice Channel Left"
        color = discord.Color.red()
    else:
        action = f"moved from {before.channel.mention} to {after.channel.mention}"
        title = "🔁 Voice Channel Moved"
        color = discord.Color.blurple()
    await send_server_log(
        member.guild,
        "voice",
        title,
        f"{member.mention} (`{member.id}`) {action}.",
        color=color,
    )


@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    changes = []
    if before.name != after.name:
        changes.append(f"Name: `{before.name}` → `{after.name}`")
    if before.verification_level != after.verification_level:
        changes.append(
            f"Verification: `{before.verification_level}` → `{after.verification_level}`"
        )
    if before.icon != after.icon:
        changes.append("Server icon changed")
    if not changes:
        return
    await send_server_log(
        after,
        "server",
        "⚙️ Server Updated",
        "Server settings were changed.",
        color=discord.Color.gold(),
        fields=[("Changes", "\n".join(changes), False)],
    )


@bot.event
async def on_invite_create(invite: discord.Invite):
    if invite.guild is None:
        return
    await send_server_log(
        invite.guild,
        "server",
        "🔗 Invite Created",
        f"Invite `{invite.code}` was created.",
        color=discord.Color.green(),
        fields=[
            ("Creator", f"{invite.inviter.mention} (`{invite.inviter.id}`)" if invite.inviter else "Unknown", False),
            ("Channel", invite.channel.mention if invite.channel else "Unknown", True),
        ],
    )


@bot.event
async def on_invite_delete(invite: discord.Invite):
    if invite.guild is None:
        return
    await send_server_log(
        invite.guild,
        "server",
        "🗑️ Invite Deleted",
        f"Invite `{invite.code}` was deleted or expired.",
        color=discord.Color.red(),
    )


@bot.listen("on_message")
async def safety_message_listener(message: discord.Message):
    """Run chat safety checks without replacing discord.py's command handler."""
    try:
        await inspect_message_for_safety(message)
    except (discord.Forbidden, discord.HTTPException) as error:
        guild_name = message.guild.name if message.guild is not None else "direct messages"
        print(f"Chat safety check failed in {guild_name}: {error}")
    except Exception as error:
        print(f"Unexpected chat safety error for message {message.id}: {error}")


@bot.hybrid_command()
async def ping(ctx: commands.Context):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")


@bot.hybrid_command()
async def membercount(ctx: commands.Context):
    member_total = ctx.guild.member_count or len(ctx.guild.members)
    embed = discord.Embed(
        title="👥 Harps Community Members",
        description=f"We currently have **{member_total:,} members** in the server!",
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)


@bot.hybrid_command(aliases=["purge"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.channel)
async def clear(ctx: commands.Context, amount: int = 10):
    if amount < 1 or amount > 100:
        await ctx.send("Choose an amount between 1 and 100.", delete_after=5)
        return
    deleted = await ctx.channel.purge(
        limit=amount + 1, check=lambda message: not message.pinned
    )
    cleared_count = max(len(deleted) - 1, 0)
    confirmation = await ctx.send(f"🧹 Cleared **{cleared_count}** messages.")
    await send_mod_log(
        ctx.guild,
        "clear",
        "🧹 Messages Cleared",
        ctx.author,
        reason="Clear command used",
        details=f"Channel: {ctx.channel.mention}\nMessages cleared: {cleared_count}",
        color=discord.Color.gold(),
    )
    await asyncio.sleep(5)
    try:
        await confirmation.delete()
    except discord.NotFound:
        pass


@bot.hybrid_command()
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"
):
    blocked = moderation_block_reason(ctx, member)
    if blocked:
        await ctx.send(blocked)
        return
    await member.kick(reason=f"{reason} | Moderator: {ctx.author} ({ctx.author.id})")
    await ctx.send(f"👢 {member} was kicked. Reason: **{reason}**")
    await send_mod_log(
        ctx.guild,
        "kick",
        "👢 Member Kicked",
        ctx.author,
        target=member,
        reason=reason,
        color=discord.Color.orange(),
    )


@bot.hybrid_command()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"
):
    blocked = moderation_block_reason(ctx, member)
    if blocked:
        await ctx.send(blocked)
        return
    await ctx.guild.ban(
        member,
        reason=f"{reason} | Moderator: {ctx.author} ({ctx.author.id})",
        delete_message_seconds=0,
    )
    await ctx.send(f"🔨 {member} was banned. Reason: **{reason}**")
    await send_mod_log(
        ctx.guild,
        "ban",
        "🔨 Member Banned",
        ctx.author,
        target=member,
        reason=reason,
        color=discord.Color.red(),
    )


@bot.hybrid_command()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban(
    ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"
):
    try:
        user = (await ctx.guild.fetch_ban(discord.Object(id=user_id))).user
    except discord.NotFound:
        await ctx.send("That user ID is not currently banned.")
        return
    await ctx.guild.unban(
        user, reason=f"{reason} | Moderator: {ctx.author} ({ctx.author.id})"
    )
    await ctx.send(f"✅ {user} was unbanned. Reason: **{reason}**")
    await send_mod_log(
        ctx.guild,
        "ban",
        "✅ Member Unbanned",
        ctx.author,
        target=user,
        reason=reason,
        color=discord.Color.green(),
    )


@bot.hybrid_command(aliases=["mute"])
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def timeout(
    ctx: commands.Context,
    member: discord.Member,
    duration: str,
    *,
    reason: str = "No reason provided",
):
    blocked = moderation_block_reason(ctx, member)
    if blocked:
        await ctx.send(blocked)
        return
    parsed_duration = parse_timeout_duration(duration)
    if parsed_duration is None:
        await ctx.send("Use a duration such as `10m`, `2h`, or `1d` (maximum 28 days).")
        return
    until = discord.utils.utcnow() + parsed_duration
    await member.timeout(
        until, reason=f"{reason} | Moderator: {ctx.author} ({ctx.author.id})"
    )
    await ctx.send(
        f"⏳ {member.mention} was timed out until "
        f"{discord.utils.format_dt(until, style='F')}."
    )
    await send_mod_log(
        ctx.guild,
        "server",
        "⏳ Member Timed Out",
        ctx.author,
        target=member,
        reason=reason,
        details=f"Duration: {duration}\nEnds: {discord.utils.format_dt(until, style='F')}",
    )


@bot.hybrid_command(aliases=["unmute"])
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def untimeout(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"
):
    blocked = moderation_block_reason(ctx, member)
    if blocked:
        await ctx.send(blocked)
        return
    await member.timeout(
        None, reason=f"{reason} | Moderator: {ctx.author} ({ctx.author.id})"
    )
    await ctx.send(f"✅ Timeout removed from {member.mention}.")
    await send_mod_log(
        ctx.guild,
        "server",
        "✅ Member Timeout Removed",
        ctx.author,
        target=member,
        reason=reason,
        color=discord.Color.green(),
    )


@bot.hybrid_command()
@commands.has_permissions(manage_messages=True)
async def warn(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"
):
    blocked = moderation_block_reason(ctx, member)
    if blocked:
        await ctx.send(blocked)
        return
    try:
        await member.send(
            f"⚠️ You received a warning in **{ctx.guild.name}**.\nReason: {reason}"
        )
        dm_status = "Warning delivered by DM"
    except discord.Forbidden:
        dm_status = "DM could not be delivered"
    await ctx.send(f"⚠️ {member.mention} was warned. Reason: **{reason}**")
    await send_mod_log(
        ctx.guild,
        "server",
        "⚠️ Member Warned",
        ctx.author,
        target=member,
        reason=reason,
        details=dm_status,
        color=discord.Color.gold(),
    )


@bot.hybrid_command()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lock(ctx: commands.Context):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        overwrite=overwrite,
        reason=f"Channel locked by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send("🔒 This channel has been locked.")
    await send_mod_log(
        ctx.guild,
        "server",
        "🔒 Channel Locked",
        ctx.author,
        reason="Lock command used",
        details=f"Channel: {ctx.channel.mention}",
    )


@bot.hybrid_command()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock(ctx: commands.Context):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        overwrite=overwrite,
        reason=f"Channel unlocked by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send("🔓 This channel has been unlocked.")
    await send_mod_log(
        ctx.guild,
        "server",
        "🔓 Channel Unlocked",
        ctx.author,
        reason="Unlock command used",
        details=f"Channel: {ctx.channel.mention}",
        color=discord.Color.green(),
    )


@bot.hybrid_command()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def slowmode(ctx: commands.Context, seconds: int = 0):
    if seconds < 0 or seconds > 21600:
        await ctx.send("Slowmode must be between 0 and 21,600 seconds.")
        return
    await ctx.channel.edit(
        slowmode_delay=seconds,
        reason=f"Slowmode changed by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send(
        "✅ Slowmode disabled."
        if seconds == 0
        else f"🐢 Slowmode set to **{seconds} seconds**."
    )
    await send_mod_log(
        ctx.guild,
        "server",
        "🐢 Slowmode Updated",
        ctx.author,
        reason="Slowmode command used",
        details=f"Channel: {ctx.channel.mention}\nDelay: {seconds} seconds",
    )


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def testwelcome(ctx: commands.Context):
    if not await send_welcome(ctx.author):
        await ctx.send(f"Welcome channel `{WELCOME_CHANNEL_NAME}` was not found.")


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def testgoodbye(ctx: commands.Context):
    if not await send_goodbye(ctx.author):
        await ctx.send(f"Goodbye channel `{GOODBYE_CHANNEL_NAME}` was not found.")


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def setupmembercount(ctx: commands.Context):
    try:
        channel = await update_member_count(ctx.guild, create_if_missing=True)
    except discord.Forbidden:
        await ctx.send(
            "I could not create the counter. Please give me the Manage Channels permission."
        )
        return
    await ctx.send(f"✅ Live member counter ready: {channel.mention}")


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_channels=True)
async def setuplogs(ctx: commands.Context):
    """Create every private server event log channel."""
    if ctx.interaction is not None:
        await ctx.defer()
    try:
        channels = await ensure_server_logging(ctx.guild)
    except (discord.Forbidden, discord.HTTPException) as error:
        await ctx.send(f"I could not create the server logs: `{error}`")
        return
    await ctx.send(
        "✅ Private server logs are ready:\n" + "\n".join(channel.mention for channel in channels)
    )


@bot.hybrid_group(name="antinuke", fallback="status")
@commands.has_permissions(administrator=True)
async def antinuke(ctx: commands.Context):
    """Show the current Harps Community anti-nuke status."""
    whitelist_role = discord.utils.get(
        ctx.guild.roles, name=ANTINUKE_WHITELIST_ROLE_NAME
    )
    log_category = discord.utils.get(
        ctx.guild.categories, name=SERVER_LOG_CATEGORY_NAME
    )
    embed = discord.Embed(
        title="🛡️ Harps Community Anti-Nuke",
        description="Anti-nuke monitoring is **enabled** whenever the bot is online.",
        color=discord.Color.green(),
    )
    embed.add_field(name="Channel deletion", value="Ban after the first confirmed deletion", inline=False)
    embed.add_field(
        name="Mass-action threshold",
        value=f"{ANTINUKE_MASS_THRESHOLD} actions within {ANTINUKE_WINDOW_SECONDS} seconds",
        inline=False,
    )
    embed.add_field(
        name="Protected actions",
        value="Role creates/deletes, role removals, kicks, bans, prunes and unauthorized bot additions",
        inline=False,
    )
    embed.add_field(
        name="Whitelist role",
        value=whitelist_role.mention if whitelist_role else "Not created",
        inline=True,
    )
    embed.add_field(
        name="Log category",
        value=log_category.name if log_category else "Not created",
        inline=True,
    )
    embed.set_footer(text="Normal joins, voluntary leaves and role additions never trigger punishment")
    await ctx.send(embed=embed)


@antinuke.command(name="setup")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(
    manage_channels=True, manage_roles=True, ban_members=True, view_audit_log=True
)
async def antinuke_setup(ctx: commands.Context):
    """Create the whitelist role and all anti-nuke/server logs."""
    if ctx.interaction is not None:
        await ctx.defer()
    try:
        role = await ensure_antinuke_whitelist_role(ctx.guild)
        channels = await ensure_server_logging(ctx.guild)
    except (discord.Forbidden, discord.HTTPException) as error:
        await ctx.send(f"Anti-nuke setup failed: `{error}`")
        return
    await ctx.send(
        f"✅ Anti-nuke is ready.\nWhitelist: {role.mention}\n"
        f"Log channels: **{len(channels)}**"
    )


@antinuke.command(name="whitelist")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_roles=True)
async def antinuke_whitelist(ctx: commands.Context, member: discord.Member):
    """Exempt a trusted member or bot from automatic anti-nuke punishment."""
    role = await ensure_antinuke_whitelist_role(ctx.guild)
    if ctx.guild.me is None or role >= ctx.guild.me.top_role:
        await ctx.send(
            f"Move my bot role above `{ANTINUKE_WHITELIST_ROLE_NAME}` first."
        )
        return
    if role in member.roles:
        await ctx.send(f"{member.mention} is already whitelisted.")
        return
    await member.add_roles(
        role, reason=f"Anti-nuke whitelist added by {ctx.author} ({ctx.author.id})"
    )
    await ctx.send(f"✅ {member.mention} is now protected by the anti-nuke whitelist.")
    await send_server_log(
        ctx.guild,
        "antinuke",
        "🛡️ Whitelist Added",
        f"{member.mention} (`{member.id}`) was whitelisted by {ctx.author.mention} (`{ctx.author.id}`).",
        color=discord.Color.green(),
    )


@antinuke.command(name="unwhitelist")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_roles=True)
async def antinuke_unwhitelist(ctx: commands.Context, member: discord.Member):
    """Remove a member or bot from the anti-nuke whitelist."""
    role = discord.utils.get(ctx.guild.roles, name=ANTINUKE_WHITELIST_ROLE_NAME)
    if role is None or role not in member.roles:
        await ctx.send(f"{member.mention} is not whitelisted.")
        return
    await member.remove_roles(
        role, reason=f"Anti-nuke whitelist removed by {ctx.author} ({ctx.author.id})"
    )
    await ctx.send(f"✅ {member.mention} was removed from the anti-nuke whitelist.")
    await send_server_log(
        ctx.guild,
        "antinuke",
        "⚠️ Whitelist Removed",
        f"{member.mention} (`{member.id}`) was unwhitelisted by {ctx.author.mention} (`{ctx.author.id}`).",
        color=discord.Color.orange(),
    )


@bot.hybrid_group(name="safety", fallback="status")
@commands.has_permissions(administrator=True)
async def safety(ctx: commands.Context):
    """Show the current Harps Community chat safety status."""
    review_channel = await get_safety_channel(
        ctx.guild, "review", create_if_missing=False
    )
    log_channel = await get_safety_channel(ctx.guild, "log", create_if_missing=False)
    whitelist_role = discord.utils.get(
        ctx.guild.roles, name=SAFETY_WHITELIST_ROLE_NAME
    )
    config = safety_config_from_channel(review_channel)
    embed = discord.Embed(
        title="🛡️ Harps Community Chat Safety",
        description=(
            "Chat safety is **enabled** whenever the bot is online. Links and actual "
            "@everyone/@here pings from non-whitelisted members cause an immediate ban. "
            "Borderline spam is removed and held for staff review."
        ),
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Rapid messages",
        value=(
            f"Review: **{config['spam_review']}** / {SAFETY_SPAM_WINDOW_SECONDS}s\n"
            f"Automatic: **{config['spam_auto']}** / {SAFETY_SPAM_WINDOW_SECONDS}s"
        ),
        inline=True,
    )
    embed.add_field(
        name="Duplicate messages",
        value=(
            f"Review: **{config['duplicate_review']}** / "
            f"{SAFETY_DUPLICATE_WINDOW_SECONDS}s\n"
            f"Automatic: **{config['duplicate_auto']}** / "
            f"{SAFETY_DUPLICATE_WINDOW_SECONDS}s"
        ),
        inline=True,
    )
    embed.add_field(
        name="Mentions per message",
        value=(
            f"Review: **{config['mention_review']}**\n"
            f"Automatic: **{config['mention_auto']}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Links and @everyone/@here",
        value="**Immediate ban** + up to 7 days of message cleanup",
        inline=False,
    )
    embed.add_field(
        name="Automatic timeout",
        value=f"**{config['timeout_minutes']} minutes**",
        inline=True,
    )
    embed.add_field(
        name="Safety whitelist",
        value=whitelist_role.mention if whitelist_role else "Not created",
        inline=True,
    )
    embed.add_field(
        name="Staff channels",
        value=(
            f"Review: {review_channel.mention if review_channel else 'Not created'}\n"
            f"Logs: {log_channel.mention if log_channel else 'Not created'}"
        ),
        inline=False,
    )
    embed.set_footer(text="Staff, bots, owners and whitelisted members are ignored")
    await ctx.send(embed=embed)


@safety.command(name="setup")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(
    manage_channels=True,
    manage_roles=True,
    manage_messages=True,
    moderate_members=True,
    ban_members=True,
)
async def safety_setup(ctx: commands.Context):
    """Create the private safety center, review queue, logs and whitelist role."""
    if ctx.interaction is not None:
        await ctx.defer()
    try:
        _, review_channel, log_channel, role = await ensure_safety_center(ctx.guild)
    except (discord.Forbidden, discord.HTTPException) as error:
        await ctx.send(f"Chat safety setup failed: `{error}`")
        return
    await ctx.send(
        "✅ Chat safety is ready.\n"
        f"Review queue: {review_channel.mention}\n"
        f"Safety logs: {log_channel.mention}\n"
        f"Whitelist: {role.mention}"
    )


@safety.command(name="whitelist")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_roles=True)
async def safety_whitelist(ctx: commands.Context, member: discord.Member):
    """Exempt a trusted member from chat safety checks."""
    role = await ensure_safety_whitelist_role(ctx.guild)
    if ctx.guild.me is None or role >= ctx.guild.me.top_role:
        await ctx.send(f"Move my bot role above `{SAFETY_WHITELIST_ROLE_NAME}` first.")
        return
    if role in member.roles:
        await ctx.send(f"{member.mention} is already safety-whitelisted.")
        return
    await member.add_roles(
        role,
        reason=f"Chat safety whitelist added by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send(f"✅ {member.mention} is now ignored by chat safety checks.")
    await send_safety_log(
        ctx.guild,
        "🛡️ Safety Whitelist Added",
        f"{member.mention} was whitelisted by {ctx.author.mention}.",
        color=discord.Color.green(),
    )


@safety.command(name="unwhitelist")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_roles=True)
async def safety_unwhitelist(ctx: commands.Context, member: discord.Member):
    """Remove a member from the chat safety whitelist."""
    role = discord.utils.get(ctx.guild.roles, name=SAFETY_WHITELIST_ROLE_NAME)
    if role is None or role not in member.roles:
        await ctx.send(f"{member.mention} is not safety-whitelisted.")
        return
    await member.remove_roles(
        role,
        reason=f"Chat safety whitelist removed by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send(f"✅ {member.mention} was removed from the safety whitelist.")
    await send_safety_log(
        ctx.guild,
        "⚠️ Safety Whitelist Removed",
        f"{member.mention} was removed by {ctx.author.mention}.",
        color=discord.Color.orange(),
    )


@safety.command(name="configure")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_channels=True)
async def safety_configure(ctx: commands.Context, setting: str, value: int):
    """Change a safety threshold stored in the private review channel topic."""
    limits = {
        "spam_review": (3, 20),
        "spam_auto": (4, 30),
        "mention_review": (2, 20),
        "mention_auto": (3, 50),
        "duplicate_review": (2, 10),
        "duplicate_auto": (3, 20),
        "timeout_minutes": (1, 1440),
    }
    setting = setting.casefold().strip()
    if setting not in limits:
        await ctx.send(
            "Unknown setting. Use one of: `" + "`, `".join(limits) + "`."
        )
        return
    minimum, maximum = limits[setting]
    if not minimum <= value <= maximum:
        await ctx.send(f"`{setting}` must be between **{minimum}** and **{maximum}**.")
        return
    _, review_channel, _, _ = await ensure_safety_center(ctx.guild)
    config = safety_config_from_channel(review_channel)
    updated = config.copy()
    updated[setting] = value
    if updated["spam_review"] >= updated["spam_auto"]:
        await ctx.send("`spam_review` must stay lower than `spam_auto`.")
        return
    if updated["mention_review"] >= updated["mention_auto"]:
        await ctx.send("`mention_review` must stay lower than `mention_auto`.")
        return
    if updated["duplicate_review"] >= updated["duplicate_auto"]:
        await ctx.send("`duplicate_review` must stay lower than `duplicate_auto`.")
        return
    await review_channel.edit(
        topic=safety_config_topic(updated),
        reason=f"Chat safety configured by {ctx.author} ({ctx.author.id})",
    )
    await ctx.send(f"✅ `{setting}` is now **{value}**.")
    await send_safety_log(
        ctx.guild,
        "⚙️ Safety Configuration Updated",
        f"`{setting}` was changed from **{config[setting]}** to **{value}** by {ctx.author.mention}.",
        color=discord.Color.blurple(),
    )


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_roles=True)
async def syncautorole(ctx: commands.Context):
    """Give the Regulars role to every current human member who is missing it."""
    role = discord.utils.get(ctx.guild.roles, name=AUTO_ROLE_NAME)
    if role is None:
        await ctx.send(f"I could not find the role `{AUTO_ROLE_NAME}`.")
        return
    if ctx.guild.me is None or role >= ctx.guild.me.top_role:
        await ctx.send(
            f"Move my bot role above `{AUTO_ROLE_NAME}` in Server Settings → Roles first."
        )
        return

    if ctx.interaction is not None:
        await ctx.defer()

    updated, failed = await sync_regular_roles(
        ctx.guild,
        f"Autorole sync requested by {ctx.author} ({ctx.author.id})",
    )

    result = f"✅ Added `{AUTO_ROLE_NAME}` to **{updated}** existing members."
    if failed:
        result += f" **{failed}** members could not be updated."
    await ctx.send(result)


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def setupmodlogs(ctx: commands.Context):
    try:
        created_channels = []
        for log_type in MOD_LOG_CHANNELS:
            channel = await get_mod_log_channel(ctx.guild, log_type)
            if channel is not None:
                created_channels.append(channel.mention)
    except discord.Forbidden:
        await ctx.send(
            "I could not create the log category. Please give me Manage Channels permission."
        )
        return
    await ctx.send(
        "✅ Moderation logs are ready:\n" + "\n".join(created_channels)
    )


@bot.hybrid_command()
@commands.has_permissions(manage_messages=True)
async def modhelp(ctx: commands.Context):
    embed = discord.Embed(
        title="🛡️ Harps Community Moderation Commands",
        description="Only members with the required Discord permissions can use these commands.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Member moderation",
        value=(
            "`!warn @member reason`\n"
            "`!timeout @member 10m reason`\n"
            "`!untimeout @member reason`\n"
            "`!kick @member reason`\n"
            "`!ban @member reason`\n"
            "`!unban USER_ID reason`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Channel moderation",
        value=(
            "`!clear 10` — clears up to 100 messages\n"
            "`!lock` / `!unlock`\n"
            "`!slowmode 10` — use 0 to disable"
        ),
        inline=False,
    )
    embed.add_field(
        name="Setup",
        value="`!setupmodlogs` — creates the private moderation log category",
        inline=False,
    )
    embed.set_footer(text="Timeout units: m = minutes, h = hours, d = days")
    await ctx.send(embed=embed)


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def rules(ctx: commands.Context):
    channel = discord.utils.get(ctx.guild.text_channels, name=RULES_CHANNEL_NAME)
    if channel is None:
        await ctx.send(f"Rules channel `{RULES_CHANNEL_NAME}` was not found.")
        return

    embed = discord.Embed(
        title="📚 Κανόνες του Harps Community",
        description=SERVER_RULES,
        color=discord.Color.blurple(),
    )
    embed.set_footer(
        text="Harps Community • Με την παραμονή σας στον server αποδέχεστε τους κανόνες"
    )
    await channel.send(embed=embed)
    await ctx.send(f"✅ Οι κανόνες δημοσιεύτηκαν στο {channel.mention}.")


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def rolerequestpanel(ctx: commands.Context):
    """Post the persistent role-request panel in the configured channel."""
    channel = discord.utils.get(
        ctx.guild.text_channels, name=ROLE_REQUEST_PANEL_CHANNEL_NAME
    )
    if channel is None:
        channel = discord.utils.find(
            lambda item: item.name.endswith("role-request"), ctx.guild.text_channels
        )
    if channel is None:
        await ctx.send(
            f"I could not find the `{ROLE_REQUEST_PANEL_CHANNEL_NAME}` channel."
        )
        return

    embed = discord.Embed(
        title="🎭 Harps Community Role Requests",
        description=(
            "Want a community role? Click **Request a Role** below, choose from the "
            "available roles and a private review channel will be created for you."
        ),
        color=discord.Color.from_rgb(171, 71, 188),
    )
    embed.add_field(
        name="📋 How it works",
        value=(
            "**1.** Click the button and choose a role.\n"
            "**2.** Add any helpful context in your private request.\n"
            "**3.** An authorized staff member will accept or deny it."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔐 Safe and private",
        value=(
            "Only you and authorized staff can see your request. Staff, managed and "
            "dangerous-permission roles are never available through this panel."
        ),
        inline=False,
    )
    if ctx.guild.icon is not None:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text="Harps Community • One open role request per member")
    await channel.send(embed=embed, view=RoleRequestPanelView())
    await ctx.send(f"✅ Role-request panel posted in {channel.mention}.")


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def boostpanel(ctx: commands.Context):
    """Post the Harps Community server-boost panel."""
    channel = discord.utils.get(
        ctx.guild.text_channels, name=BOOST_PANEL_CHANNEL_NAME
    )
    if channel is None:
        channel = discord.utils.find(
            lambda item: item.name.endswith("server-boost"), ctx.guild.text_channels
        )
    if channel is None:
        await ctx.send(f"I could not find the `{BOOST_PANEL_CHANNEL_NAME}` channel.")
        return

    boost_count = ctx.guild.premium_subscription_count or 0
    boost_level = int(ctx.guild.premium_tier)
    embed = discord.Embed(
        title="🚀 Boost Harps Community",
        description=(
            "Help us level up Harps Community! Every boost supports the entire server "
            "and helps unlock better community features for everyone. 💜"
        ),
        color=discord.Color.from_rgb(244, 127, 255),
    )
    embed.add_field(
        name="✨ Why boost?",
        value=(
            "Boosts help unlock more emoji, sticker and soundboard slots, better server "
            "customization and other Discord perks for the whole community."
        ),
        inline=False,
    )
    embed.add_field(name="🚀 Current boosts", value=f"**{boost_count:,}**", inline=True)
    embed.add_field(name="💎 Server level", value=f"**Level {boost_level}**", inline=True)
    embed.add_field(
        name="💜 Thank you",
        value="Every booster directly helps the community. We truly appreciate your support!",
        inline=False,
    )
    if ctx.guild.icon is not None:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    banner_url = server_banner_url(ctx.guild)
    if banner_url is not None:
        embed.set_image(url=banner_url)
    embed.set_footer(text="Harps Community • Thank you for helping us grow!")

    await channel.send(embed=embed, view=BoostPanelView())
    await ctx.send(f"✅ Server-boost panel posted in {channel.mention}.")


async def upsert_lfg_embed(
    channel: discord.TextChannel,
    title: str,
    embed: discord.Embed,
    *,
    view: discord.ui.View | None = None,
) -> discord.Message:
    async for message in channel.history(limit=50):
        if (
            bot.user is not None
            and message.author.id == bot.user.id
            and message.embeds
            and message.embeds[0].title == title
        ):
            await message.edit(
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return message
    return await channel.send(
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.hybrid_group(name="lfg", fallback="status")
@commands.has_permissions(administrator=True)
async def lfg(ctx: commands.Context):
    """Show the Harps Community LFG system status."""
    category = discord.utils.get(ctx.guild.categories, name=LFG_CATEGORY_NAME)
    active_channel = await get_lfg_channel(
        ctx.guild, "active", create_if_missing=False
    )
    active_count = 0
    if isinstance(active_channel, discord.TextChannel):
        async for message in active_channel.history(limit=200):
            metadata = lfg_metadata(message)
            if metadata is not None and message.embeds and lfg_status(
                message.embeds[0]
            ) in {"🟢 Open", "🔴 Full"}:
                active_count += 1
    embed = discord.Embed(
        title="🎮 Harps Community LFG",
        description=(
            "The LFG system lets members build Duos, Trios, Squads, 5 Stacks and "
            "custom teams using persistent interactive listings."
        ),
        color=discord.Color.green() if category else discord.Color.orange(),
    )
    embed.add_field(
        name="Status", value="✅ Ready" if category else "⚠️ Not set up", inline=True
    )
    embed.add_field(name="Active listings", value=str(active_count), inline=True)
    embed.add_field(name="Listing lifetime", value=f"{LFG_EXPIRY_HOURS} hours", inline=True)
    embed.add_field(
        name="Supported games",
        value=", ".join(LFG_GAMES.values()),
        inline=False,
    )
    embed.add_field(
        name="Setup command", value="Run `/lfg setup` once as an administrator.", inline=False
    )
    await ctx.send(embed=embed)


@lfg.command(name="setup")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(
    manage_channels=True,
    manage_messages=True,
    move_members=True,
    view_channel=True,
    send_messages=True,
)
async def lfg_setup(ctx: commands.Context):
    """Create or repair the complete LFG category, channels and panels."""
    if ctx.interaction is not None:
        await ctx.defer()
    try:
        channels = await ensure_lfg_hub(ctx.guild)
        rules_channel = channels["rules"]
        create_channel = channels["create"]
        if not isinstance(rules_channel, discord.TextChannel) or not isinstance(
            create_channel, discord.TextChannel
        ):
            raise RuntimeError("The LFG text channels could not be created.")

        rules_embed = discord.Embed(
            title="📌 Harps Community LFG Rules",
            description=(
                "Use LFG to find friendly teammates and build Duos, Trios, Squads or "
                "full competitive teams. Keep every listing honest, respectful and safe."
            ),
            color=discord.Color.blurple(),
        )
        rules_embed.add_field(
            name="Community rules",
            value=(
                "• No harassment, discrimination, trolling or toxic requirements.\n"
                "• No links, Discord invites, advertisements, boosting or account sales.\n"
                "• Do not share private information.\n"
                "• Use accurate game, region, platform and rank information.\n"
                "• Close your listing when the session is finished."
            ),
            inline=False,
        )
        rules_embed.add_field(
            name="Voice rooms",
            value=(
                f"Join **{LFG_VOICE_CREATOR_NAME}** to receive a temporary room. "
                "It is removed automatically when everyone leaves."
            ),
            inline=False,
        )
        rules_embed.set_footer(text="Harps Community • Play together, respect everyone")
        await upsert_lfg_embed(
            rules_channel, "📌 Harps Community LFG Rules", rules_embed
        )

        panel_embed = discord.Embed(
            title="🎮 Find Your Team",
            description=(
                "Ready to play? Create a detailed LFG listing and let other Harps "
                "Community members join your team."
            ),
            color=discord.Color.blurple(),
        )
        panel_embed.add_field(
            name="How it works",
            value=(
                "1. Press **Create LFG**.\n"
                "2. Choose your game, team size, region and platform.\n"
                "3. Add language, microphone, rank, schedule and requirements.\n"
                "4. Manage your team from the listing buttons."
            ),
            inline=False,
        )
        panel_embed.add_field(
            name="Available formats",
            value="Duo • Trio • Squad • 5 Stack • Custom Team",
            inline=False,
        )
        panel_embed.add_field(
            name="Automatic cleanup",
            value=f"Listings expire after **{LFG_EXPIRY_HOURS} hours**.",
            inline=False,
        )
        panel_embed.set_footer(text="Harps Community • Looking For Group")
        panel_message = await upsert_lfg_embed(
            create_channel,
            "🎮 Find Your Team",
            panel_embed,
            view=LFGCreatePanelView(),
        )
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
        await ctx.send(f"LFG setup failed: `{error}`")
        return

    await send_lfg_log(
        ctx.guild,
        "⚙️ LFG System Set Up",
        f"The LFG hub was created or repaired by {ctx.author.mention}.",
        color=discord.Color.green(),
    )
    await ctx.send(
        "✅ LFG is ready.\n"
        f"Create panel: {panel_message.jump_url}\n"
        f"Active listings: {channels['active'].mention}\n"
        f"Voice creator: {channels['voice'].mention}"
    )


@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def ticketpanel(ctx: commands.Context):
    embed = discord.Embed(
        title="🎫 Harps Community Support",
        description=(
            "Need assistance? Choose the option that best matches your request below.\n\n"
            "A private ticket will be created for you and the Harps Community staff team."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Support options",
        value=(
            "🎫 **General Support** — Questions or server help\n"
            "🚨 **Report a Member** — Privately report an issue\n"
            "🤝 **Partnership / Other** — Partnerships and other enquiries"
        ),
        inline=False,
    )
    embed.set_footer(text="Harps Community • Please open only one ticket per topic")
    await ctx.send(embed=embed, view=TicketPanelView())


@ticketpanel.error
@boostpanel.error
@rolerequestpanel.error
@rules.error
@lfg_setup.error
@lfg.error
@safety_configure.error
@safety_unwhitelist.error
@safety_whitelist.error
@safety_setup.error
@safety.error
@antinuke_unwhitelist.error
@antinuke_whitelist.error
@antinuke_setup.error
@antinuke.error
@setuplogs.error
@syncautorole.error
@setupmodlogs.error
@setupmembercount.error
@testwelcome.error
@testgoodbye.error
async def admin_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Administrator permission to use this command.")
        return
    if isinstance(error, commands.BotMissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        await ctx.send(f"I need the following permission(s): `{permissions}`.")
        return
    raise error


@clear.error
@kick.error
@ban.error
@unban.error
@timeout.error
@untimeout.error
@warn.error
@lock.error
@unlock.error
@slowmode.error
@modhelp.error
async def moderation_command_error(
    ctx: commands.Context, error: commands.CommandError
):
    if isinstance(error, commands.MissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        await ctx.send(f"You do not have the required permission(s): `{permissions}`.")
    elif isinstance(error, commands.BotMissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        await ctx.send(f"I need the following permission(s): `{permissions}`.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required value: `{error.param.name}`. Use `!modhelp` for examples.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("I could not find that member. Mention them or use their user ID.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("One of those values is invalid. Use `!modhelp` for examples.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Please wait {error.retry_after:.1f} seconds before using that again.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command can only be used inside the server.")
    else:
        raise error


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

bot.run(TOKEN)
