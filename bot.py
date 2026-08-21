import asyncio
import io
import os
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands


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
SERVER_LOG_CATEGORY_NAME = "📋 SERVER LOGS"
ANTINUKE_WHITELIST_ROLE_NAME = "🛡️ Anti-Nuke Whitelist"
ANTINUKE_MASS_THRESHOLD = 3
ANTINUKE_WINDOW_SECONDS = 10

# IDs placed here are always trusted, including bots that are not in the server yet.
ANTINUKE_WHITELIST_IDS: set[int] = set()

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
antinuke_activity: dict[tuple[int, int, str], deque[float]] = defaultdict(deque)
antinuke_triggered: set[tuple[int, int]] = set()
server_log_setup_locks: dict[int, asyncio.Lock] = {}
recent_member_removals: dict[int, deque[tuple[float, int]]] = defaultdict(deque)
last_member_removal_check: dict[int, float] = {}
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

    embed = discord.Embed(
        title="👋 Welcome to Harps Community!",
        description=f"Welcome {member.mention}! Hope you enjoy your stay.",
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"👥 Member #{member.guild.member_count}")
    await channel.send(embed=embed)
    return True


async def send_goodbye(member: discord.Member) -> bool:
    channel = discord.utils.get(member.guild.text_channels, name=GOODBYE_CHANNEL_NAME)
    if channel is None:
        return False

    embed = discord.Embed(
        title="👋 Goodbye from Harps Community",
        description=f"**{member.display_name}** has left the server. We hope to see them again!",
        color=discord.Color.red(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"👥 Members remaining: {member.guild.member_count}")
    await channel.send(embed=embed)
    return True


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


# Register persistent views before connecting so their buttons survive restarts.
bot.add_view(TicketPanelView())
bot.add_view(CloseTicketView())


@bot.event
async def on_ready():
    global slash_commands_synced
    print(f"✅ Logged in as {bot.user}")
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


@bot.event
async def on_voice_state_update(
    member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
):
    if before.channel == after.channel:
        return
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
@rules.error
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
