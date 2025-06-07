#bot.py
import discord
from discord.ext import commands, tasks
import aiohttp
import time
import os
from dotenv import load_dotenv
import json

# Load env variables
load_dotenv()

# Get Discord bot token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Define intents to enable message and member events
intents = discord.Intents.default()
intents.messages = True
intents.members = True

# Create a Discord bot instance
client = commands.Bot(command_prefix="!", intents=intents)

# Define a global variable to store the previous XeggeX value
last_notification_time = 0

# Function to set a voice channel to private (disconnect for everyone)
async def set_channel_private(category, channel):
    try:
        if isinstance(channel, discord.VoiceChannel) and channel.category == category:
            await channel.set_permissions(channel.guild.default_role, connect=False)
    except Exception as e:
        print(f"An error occurred while setting channel to private: {e}")

# Function to get or create a voice channel within a category
async def get_or_create_channel(category, channel_name):
    for existing_channel in category.voice_channels:
        existing_name = existing_channel.name.lower().replace(" ", "")
        target_name = channel_name.lower().replace(" ", "")
        if existing_name.startswith(target_name):
            return existing_channel

    channel = await category.create_voice_channel(channel_name)
    time.sleep(0.5)
    return channel

# Function to create or update a voice channel's name with specific formatting
async def create_or_update_channel(guild, category, channel_name, stat_value):
    try:
        channel = await get_or_create_channel(category, channel_name)

        if isinstance(stat_value, str) and stat_value == "N/A":
            formatted_value = stat_value
        else:
            if channel_name.lower() == "members:":
                formatted_value = "{:,.0f}".format(stat_value)
            elif channel_name.lower() == "supply:":
                formatted_value = "{:,.2f}B MEWC".format(stat_value)
            elif channel_name.lower() == "price: $":
                formatted_value = "{:.6f}".format(stat_value)
            elif channel_name.lower() == "hashrate: gh/s":
                formatted_value = "{:,.3f}".format(stat_value)
            elif channel_name.lower() == "market cap:":
                formatted_value = "{:,.0f}".format(round(stat_value))
            elif channel_name.lower() in ["difficulty:", "block:"]:
                formatted_value = "{:,.0f}".format(stat_value)
            elif channel_name.lower() == "24h volume:":
                formatted_value = "{:,.0f}".format(stat_value)
            else:
                formatted_value = stat_value

        await channel.edit(name=f"{channel_name} {formatted_value}")

    except Exception as e:
        print(f"An error occurred while updating channel name: {e}")

# Function to update all statistics channels within a guild
async def update_stats_channels(guild):
    global last_notification_time

    try:
        # Fetch server statistics from the APIs
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://mewc.cryptoscope.io/api/getdifficulty") as response:
                    difficulty_data = await response.json()
                    difficulty = difficulty_data["difficulty_raw"]
            except Exception:
                difficulty = "N/A"

            try:
                async with session.get("https://mewc.cryptoscope.io/api/getnetworkhashps") as response:
                    hashrate_data = await response.json()
                    hashrate = hashrate_data["hashrate_raw"] / 1e9  # Convert to GH/s
            except Exception:
                hashrate = "N/A"

            try:
                async with session.get("https://mewc.cryptoscope.io/api/getblockcount") as response:
                    block_data = await response.json()
                    block_count = block_data["blockcount"]
            except Exception:
                block_count = "N/A"

            try:
                async with session.get("https://mewc.cryptoscope.io/api/getcoinsupply") as response:
                    supply_data = await response.json()
                    supply = float(supply_data["coinsupply"]) / 1_000_000_000  # Already in billions
            except Exception:
                supply = "N/A"

            # --- EXCHANGE DATA COLLECTION ---
            # Xeggex
            try:
                async with session.get("https://api.xeggex.com/api/v2/market/getbysymbol/mewc_usdt") as response:
                    price_data = await response.json()
                    xeggex_price = float(price_data["lastPrice"])
                    xeggex_volume = float(price_data["volume"]) * xeggex_price
                    xeggex_change = float(price_data.get("changePercent", 0))
            except Exception:
                xeggex_price = "N/A"
                xeggex_volume = "N/A"
                xeggex_change = "N/A"

            # TradeOgre
            try:
                async with session.get("https://tradeogre.com/api/v1/ticker/mewc-usdt") as response:
                    text_data = await response.text()
                    tradeogre_data = json.loads(text_data)
                    tradeogre_price = float(tradeogre_data["price"])
                    tradeogre_volume = float(tradeogre_data["volume"])
                    # Calculate percent change from initialprice
                    initial_price = float(tradeogre_data.get("initialprice", tradeogre_price))
                    if initial_price > 0:
                        tradeogre_change = ((tradeogre_price - initial_price) / initial_price) * 100
                    else:
                        tradeogre_change = 0
            except Exception:
                tradeogre_price = "N/A"
                tradeogre_volume = "N/A"
                tradeogre_change = "N/A"

            # --- WEIGHTED AVERAGE CALCULATION ---
            available_exchanges = []
            if xeggex_price != "N/A" and xeggex_volume != "N/A":
                available_exchanges.append({
                    "name": "XeggeX",
                    "price": xeggex_price,
                    "volume": xeggex_volume,
                    "change": xeggex_change
                })
            if tradeogre_price != "N/A" and tradeogre_volume != "N/A":
                available_exchanges.append({
                    "name": "TradeOgre",
                    "price": tradeogre_price,
                    "volume": tradeogre_volume,
                    "change": tradeogre_change
                })

            # Print which exchanges are being used
            print("\nExchanges being used:")
            for ex in available_exchanges:
                print(f"{ex['name']} - Price: ${ex['price']:.6f}, Volume: ${ex['volume']:,.2f}")
            print(f"Total exchanges used: {len(available_exchanges)}\n")

            if available_exchanges:
                total_volume = sum(ex["volume"] for ex in available_exchanges)
                weighted_price = sum(ex["price"] * (ex["volume"] / total_volume) for ex in available_exchanges)
                # Weighted average of price change if available
                available_changes = [ex for ex in available_exchanges if ex["change"] != "N/A"]
                if available_changes:
                    weighted_change = sum(
                        float(ex["change"]) * (ex["volume"] / total_volume)
                        for ex in available_changes
                    )
                    if weighted_change >= 0:
                        price_display = f"${weighted_price:.6f} (▲ +{weighted_change:.2f}% 24h)"
                    else:
                        price_display = f"${weighted_price:.6f} (▼ {weighted_change:.2f}% 24h)"
                else:
                    price_display = f"${weighted_price:.6f}"
            else:
                weighted_price = "N/A"
                price_display = "N/A"
                total_volume = "N/A"

        try:
            member_count = guild.member_count
        except Exception:
            member_count = "N/A"

        # Define the category name for statistics channels
        category_name = "Meowcoin Server Stats"
        category = discord.utils.get(guild.categories, name=category_name)

        if not category:
            print(f"Creating category '{category_name}'")
            category = await guild.create_category(category_name)

        time.sleep(0.5)

        # Update or create individual statistics channels
        print(f"Members '{member_count}'")
        await create_or_update_channel(guild, category, "Members:", member_count)
        time.sleep(0.5)
        print(f"Difficulty '{difficulty}'")
        await create_or_update_channel(guild, category, "Difficulty:", difficulty)
        time.sleep(0.5)
        print(f"Hashrate '{hashrate}'")
        await create_or_update_channel(guild, category, "Hashrate: GH/s", hashrate)
        time.sleep(0.5)
        print(f"Block '{block_count}'")
        await create_or_update_channel(guild, category, "Block:", block_count)
        time.sleep(0.5)
        print(f"Supply '{supply}'")
        await create_or_update_channel(guild, category, "Supply:", supply)
        time.sleep(0.5)
        print(f"Price '{price_display}'")
        await create_or_update_channel(guild, category, "Price:", price_display)
        time.sleep(0.5)
        # Ensure volume is formatted correctly
        if total_volume != "N/A":
            formatted_volume = "{:,.0f}".format(total_volume)
        else:
            formatted_volume = "N/A"
        print(f"24h Volume '{formatted_volume}'")
        await create_or_update_channel(guild, category, "24h Volume: $", formatted_volume)
        time.sleep(0.5)
        # Calculate market cap and ensure it's formatted correctly
        if supply != "N/A" and weighted_price != "N/A":
            market_cap = round(supply * weighted_price * 1_000_000_000)  # supply is in billions
            formatted_market_cap = "{:,.0f}".format(market_cap)
        else:
            formatted_market_cap = "N/A"
        print(f"Market Cap '{formatted_market_cap}'")
        await create_or_update_channel(guild, category, "Market Cap: $", formatted_market_cap)
        time.sleep(0.5)
        # Set all channels to private
        for channel in category.voice_channels:
            await set_channel_private(category, channel)

    except Exception as e:
        print(f"An error occurred while updating channels: {e}")

# Define a task to update statistics channels every 5 minutes
@tasks.loop(minutes=5)
async def update_stats_task():
    for guild in client.guilds:
        print(f"Updating stats for guild '{guild.name}'")
        await update_stats_channels(guild)

@client.event
async def on_ready():
    print("The bot is ready")
    update_stats_task.start()

# Run the bot with the provided token
client.run(TOKEN)
