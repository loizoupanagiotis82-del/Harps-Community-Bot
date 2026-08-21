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
    channel = discord.utils.get(member.guild.text_channels, name="📜・welcome")

    if channel:
        embed = discord.Embed(
            title="👋 Welcome to Harps Community!",
            description=f"Welcome {member.mention}! Hope you enjoy your stay.",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"👥 Member #{member.guild.member_count}")

        await channel.send(embed=embed)
bot.run(TOKEN)