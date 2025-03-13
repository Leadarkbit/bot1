import os
import discord
from discord.ext import commands
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import hashlib
import json
import re
import sys
import importlib.util

# Importer le fichier de configuration
try:
    spec = importlib.util.spec_from_file_location("config", "config.py")
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
except Exception as e:
    print(f"Erreur lors du chargement de config.py: {e}")
    config = None

class Crypto(commands.Cog):
    """Cog pour le chiffrement et déchiffrement des messages"""
    
    def __init__(self, bot):
        self.bot = bot
        # Récupérer la clé de chiffrement depuis config.py, puis des variables d'environnement, ou en générer une nouvelle
        self.encryption_key = None
        
        # Essayer d'abord de récupérer depuis config.py
        if config and hasattr(config, 'ENCRYPTION_KEY') and config.ENCRYPTION_KEY:
            self.encryption_key = config.ENCRYPTION_KEY
            print("🔐 Clé de chiffrement chargée depuis config.py")
        
        # Sinon, essayer les variables d'environnement
        if not self.encryption_key:
            self.encryption_key = os.getenv('ENCRYPTION_KEY')
            if self.encryption_key:
                print("🔐 Clé de chiffrement chargée depuis les variables d'environnement")
        
        # En dernier recours, générer une clé temporaire
        if not self.encryption_key:
            # Générer une clé aléatoire si aucune n'est définie
            import secrets
            self.encryption_key = secrets.token_hex(32)  # 32 bytes = 256 bits
            print(f"⚠️ Aucune clé de chiffrement trouvée. Une clé temporaire a été générée.")
            print(f"⚠️ Pour une sécurité permanente, ajoutez cette clé à votre fichier config.py : ENCRYPTION_KEY={self.encryption_key}")
        
        # Convertir la clé hexadécimale en bytes
        self.key = bytes.fromhex(self.encryption_key) if len(self.encryption_key) == 64 else hashlib.sha256(self.encryption_key.encode()).digest()
        
        # Préfixe pour identifier les messages chiffrés
        self.encrypted_prefix = "🔒 "
        
        # Commandes pour le chiffrement/déchiffrement à la fin des messages (simplifiées)
        self.encrypt_command = "-e"
        self.decrypt_command = "-d"
        
        print("🔐 Module de chiffrement initialisé avec succès!")
        print(f"🔑 Clé de chiffrement: {self.encryption_key[:8]}...{self.encryption_key[-8:]}")
    
    def encrypt(self, plaintext):
        """Chiffrer un message avec AES-256"""
        try:
            # Convertir le texte en JSON pour préserver les métadonnées
            data = {
                "content": plaintext,
                "timestamp": discord.utils.utcnow().timestamp()
            }
            plaintext_json = json.dumps(data)
            
            # Générer un IV aléatoire
            iv = os.urandom(16)
            
            # Créer un padder pour s'assurer que le texte a la bonne longueur
            padder = padding.PKCS7(algorithms.AES.block_size).padder()
            padded_data = padder.update(plaintext_json.encode()) + padder.finalize()
            
            # Créer le chiffreur
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            
            # Chiffrer les données
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # Combiner IV et texte chiffré et encoder en base64
            encrypted_message = base64.b64encode(iv + ciphertext).decode('utf-8')
            
            # Ajouter le préfixe pour identifier les messages chiffrés
            return f"{self.encrypted_prefix}{encrypted_message}"
        except Exception as e:
            print(f"Erreur lors du chiffrement: {str(e)}")
            return f"⚠️ Erreur de chiffrement: {str(e)}"
    
    def decrypt(self, encrypted_message):
        """Déchiffrer un message chiffré avec AES-256"""
        try:
            # Nettoyer le message pour enlever les espaces et mentions potentielles
            cleaned_message = encrypted_message.strip()
            
            # Extraire le message chiffré en cherchant le préfixe
            match = re.search(r'(🔒\s+[A-Za-z0-9+/=]+)', cleaned_message)
            if not match:
                return encrypted_message
            
            # Extraire la partie chiffrée
            encrypted_part = match.group(1)
            
            # Vérifier si le message est chiffré
            if not encrypted_part.startswith(self.encrypted_prefix):
                return encrypted_message
            
            # Extraire le message chiffré
            encrypted_data = encrypted_part[len(self.encrypted_prefix):].strip()
            
            # Décoder le message de base64
            encrypted_bytes = base64.b64decode(encrypted_data)
            
            # Extraire l'IV (les 16 premiers octets)
            iv = encrypted_bytes[:16]
            ciphertext = encrypted_bytes[16:]
            
            # Créer le déchiffreur
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            
            # Déchiffrer les données
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Supprimer le padding
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            
            # Convertir les données JSON en dictionnaire
            json_data = json.loads(data.decode('utf-8'))
            
            # Retourner le contenu du message
            return json_data["content"]
        except Exception as e:
            print(f"Erreur lors du déchiffrement: {str(e)}")
            return f"⚠️ Impossible de déchiffrer ce message: {str(e)}"
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Intercepter les messages pour les chiffrer ou déchiffrer selon la commande"""
        # Ignorer les messages du bot lui-même
        if message.author.bot:
            return
        
        # Vérifier si le message contient une commande de chiffrement
        if message.content.endswith(self.encrypt_command):
            # Extraire le message sans la commande
            original_content = message.content[:-len(self.encrypt_command)].strip()
            
            # Chiffrer le message
            encrypted_content = self.encrypt(original_content)
            
            # Supprimer le message original
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass  # Le message a déjà été supprimé
            
            # Envoyer le message chiffré
            await message.channel.send(
                f"{message.author.mention}: {encrypted_content}",
                files=[await attachment.to_file() for attachment in message.attachments]
            )
            return
        
        # Vérifier si le message contient une commande de déchiffrement
        if message.content.endswith(self.decrypt_command):
            # Extraire le message sans la commande
            encrypted_content = message.content[:-len(self.decrypt_command)].strip()
            
            # Chercher le message chiffré dans le texte
            match = re.search(r'(🔒\s+[A-Za-z0-9+/=]+)', encrypted_content)
            if not match:
                await message.channel.send("❌ Ce message ne contient pas de contenu chiffré.")
                return
            
            # Extraire la partie chiffrée
            encrypted_part = match.group(1)
            
            # Déchiffrer le message
            decrypted_content = self.decrypt(encrypted_part)
            
            # Supprimer le message original
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass  # Le message a déjà été supprimé
            
            # Envoyer le message déchiffré
            await message.channel.send(
                f"{message.author.mention}: 🔓 {decrypted_content}",
                files=[await attachment.to_file() for attachment in message.attachments]
            )
            return
    
    @commands.command(name="encrypt")
    async def encrypt_message(self, ctx, *, plaintext=None):
        """Chiffrer un message manuellement
        
        Usage: !encrypt [message]
        Si aucun message n'est fourni, chiffre le message auquel vous répondez.
        """
        # Si aucun message n'est fourni, vérifier s'il s'agit d'une réponse à un message
        if not plaintext and ctx.message.reference:
            referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            plaintext = referenced_message.content
        
        if not plaintext:
            await ctx.send("❌ Veuillez fournir un message à chiffrer ou répondre à un message.")
            return
        
        # Chiffrer le message
        encrypted_message = self.encrypt(plaintext)
        
        # Envoyer le message chiffré
        await ctx.send(f"🔒 Message chiffré: {encrypted_message}")
    
    @commands.command(name="decrypt")
    async def decrypt_message(self, ctx, *, encrypted_message=None):
        """Déchiffrer un message manuellement
        
        Usage: !decrypt [message chiffré]
        Si aucun message n'est fourni, déchiffre le message auquel vous répondez.
        """
        # Si aucun message n'est fourni, vérifier s'il s'agit d'une réponse à un message
        if not encrypted_message and ctx.message.reference:
            referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            encrypted_message = referenced_message.content
        
        if not encrypted_message:
            await ctx.send("❌ Veuillez fournir un message à déchiffrer ou répondre à un message chiffré.")
            return
        
        # Chercher le message chiffré dans le texte
        match = re.search(r'(🔒\s+[A-Za-z0-9+/=]+)', encrypted_message)
        if not match:
            await ctx.send("❌ Ce message ne contient pas de contenu chiffré.")
            return
            
        # Extraire la partie chiffrée
        encrypted_part = match.group(1)
        
        # Déchiffrer le message
        decrypted_message = self.decrypt(encrypted_part)
        
        # Envoyer le message déchiffré
        await ctx.send(f"🔓 Message déchiffré: {decrypted_message}")
    
    @commands.command(name="crypto_help")
    async def crypto_help(self, ctx):
        """Afficher l'aide pour les commandes de chiffrement"""
        embed = discord.Embed(
            title="🔐 Aide Chiffrement",
            description="Comment utiliser le système de chiffrement",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Chiffrer un message",
            value="Ajoutez `-e` à la fin de votre message pour le chiffrer automatiquement.\n"
                  "Exemple: `Ceci est un message secret -e`",
            inline=False
        )
        
        embed.add_field(
            name="Déchiffrer un message",
            value="Copiez un message chiffré et ajoutez `-d` à la fin pour le déchiffrer.\n"
                  "Exemple: `🔒 ABC123... -d`",
            inline=False
        )
        
        embed.add_field(
            name="Commandes classiques",
            value="• `!encrypt [message]` - Chiffrer un message\n"
                  "• `!decrypt [message]` - Déchiffrer un message\n"
                  "• `!crypto_help` - Afficher cette aide",
            inline=False
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Crypto(bot)) 