import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Nécessaire pour accéder à la liste des membres du serveur
intents.presences = True  # Nécessaire pour détecter les changements de statut
bot = commands.Bot(command_prefix='!', intents=intents)

# Load cogs
async def load_extensions():
    await bot.load_extension("cogs.exploiter")
    await bot.load_extension("cogs.sentinel")
    await bot.load_extension("cogs.crypto")  # Charger le module de chiffrement
    await bot.load_extension("cogs.security")  # Charger le module de sécurité
    await bot.load_extension("cogs.shadowban")  # Charger le module de shadow ban
    await bot.load_extension("cogs.antiscam")  # Charger le module anti-arnaque

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot is connected to {len(bot.guilds)} guilds')
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="for security threats"
    ))

@bot.event
async def setup_hook():
    await load_extensions()

# Run the bot
if __name__ == "__main__":
    # Récupérer le token depuis les variables d'environnement
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("⚠️ ERREUR: Token Discord non trouvé dans le fichier .env")
        print("Assurez-vous que le fichier .env existe et contient DISCORD_TOKEN=votre_token")
        exit(1)
    
    bot.run(token) 