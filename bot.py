import asyncio
import io
import os
import re

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
WELCOME_CHANNEL_NAME = "📜・welcome"
GOODBYE_CHANNEL_NAME = "📜・goodbye"

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
    print(f"✅ Logged in as {bot.user}")


@bot.event
async def on_member_join(member: discord.Member):
    await send_welcome(member)


@bot.event
async def on_member_remove(member: discord.Member):
    await send_goodbye(member)


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")


@bot.command()
@commands.has_permissions(administrator=True)
async def testwelcome(ctx: commands.Context):
    if not await send_welcome(ctx.author):
        await ctx.send(f"Welcome channel `{WELCOME_CHANNEL_NAME}` was not found.")


@bot.command()
@commands.has_permissions(administrator=True)
async def testgoodbye(ctx: commands.Context):
    if not await send_goodbye(ctx.author):
        await ctx.send(f"Goodbye channel `{GOODBYE_CHANNEL_NAME}` was not found.")


@bot.command()
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
@testwelcome.error
@testgoodbye.error
async def admin_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Administrator permission to use this command.")
        return
    raise error


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

bot.run(TOKEN)
