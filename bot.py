import discord
from discord.ext import commands

TOKEN = "MTU0MDM0NDkwNjE2NDQ3ODAxMg.G-YzeQ.2wqtfzw3vA7nRkDrQt3ibZ6Cu_zr2vco41WKdU"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")
@bot.event
async def on_member_join(member):
    channel = discord.utils.get(
        member.guild.text_channels,
        name="📜・welcome"
    )

    if channel:
        embed = discord.Embed(
            title="✨ WELCOME TO HARPS COMMUNITY",
            description=(
                f"### Welcome, {member.mention}! 👋\n"
                f"We're happy to have you with us.\n\n"
                f"🌟 **Enjoy your stay & have fun!**"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
            timestamp=discord.utils.utcnow()
        )

        # Member's profile picture
        embed.set_thumbnail(url=member.display_avatar.url)

        # Small footer
        embed.set_footer(
            text=f"Harps Community  •  Member #{member.guild.member_count}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )

        await channel.send(
            content=f"🎉 {member.mention}",
            embed=embed
        )
@bot.command()
@commands.has_permissions(administrator=True)
async def testwelcome(ctx):
    member = ctx.author

    embed = discord.Embed(
        title="✨ WELCOME TO HARPS COMMUNITY",
        description=(
            f"### Welcome, {member.mention}! 👋\n"
            f"We're happy to have you with us.\n\n"
            f"🌟 **Enjoy your stay & have fun!**"
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=discord.utils.utcnow()
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.set_footer(
        text=f"Harps Community  •  Member #{member.guild.member_count}",
        icon_url=member.guild.icon.url if member.guild.icon else None
    )

    await ctx.send(embed=embed)
bot.run(TOKEN)
