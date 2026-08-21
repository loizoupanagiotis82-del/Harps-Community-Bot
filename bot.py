import asyncio
import io
import os
import re
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
            synced_commands = await bot.tree.sync()
        except discord.HTTPException as error:
            print(f"Could not sync slash commands: {error}")
        else:
            slash_commands_synced = True
            print(f"✅ Synced {len(synced_commands)} slash commands")
    for guild in bot.guilds:
        try:
            await update_member_count(guild)
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Could not update member counter in {guild.name}: {error}")


@bot.event
async def on_member_join(member: discord.Member):
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
@setupmodlogs.error
@setupmembercount.error
@testwelcome.error
@testgoodbye.error
async def admin_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Administrator permission to use this command.")
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
