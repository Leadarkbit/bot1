import discord
from discord.ext import commands
import os
import json
import random
import asyncio
from datetime import datetime
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

class ShadowBan(commands.Cog):
    """Système de shadow ban permettant de rendre un utilisateur invisible sans qu'il le sache"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "data/shadowban_db.json"
        self.shadowbanned_users = {}  # {user_id: {mode: "delete|modify|invisible", timestamp: datetime}}
        self.nonsense_messages = [
            "Je ne comprends pas pourquoi personne ne répond à mes messages...",
            "Est-ce que quelqu'un peut me voir ?",
            "Bonjour ? Il y a quelqu'un ?",
            "Je pense que Discord a un problème aujourd'hui.",
            "Pourquoi personne ne me répond ?",
            "Je crois que mon message n'est pas passé.",
            "Internet est vraiment lent aujourd'hui.",
            "Est-ce que le serveur est down ?",
            "Je vais essayer de me reconnecter plus tard.",
            "Discord bug encore une fois..."
        ]
        
        # Récupérer l'ID du canal d'alerte depuis config.py ou les variables d'environnement
        if config and hasattr(config, 'SECURITY_LOG_CHANNEL_ID'):
            self.alert_channel_id = config.SECURITY_LOG_CHANNEL_ID
            print("📢 Canal d'alerte chargé depuis config.py")
        else:
            self.alert_channel_id = os.getenv('SECURITY_LOG_CHANNEL_ID')
            print("📢 Canal d'alerte chargé depuis les variables d'environnement")
            
        self.message_cache = {}  # Pour stocker temporairement les messages supprimés
        
        # Créer le dossier data s'il n'existe pas
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        
        # Charger la base de données
        self.load_db()
        
        print("🥷 Module de shadow ban initialisé!")
        print(f"👻 Utilisateurs actuellement shadow-ban: {len(self.shadowbanned_users)}")
    
    def load_db(self):
        """Charger la liste des utilisateurs shadow-ban"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r') as f:
                    data = json.load(f)
                    self.shadowbanned_users = data
                print(f"✅ Base de données shadow ban chargée: {len(self.shadowbanned_users)} utilisateurs")
            else:
                self.save_db()
                print("✅ Nouvelle base de données shadow ban créée")
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement de la base de données: {str(e)}")
            self.shadowbanned_users = {}
    
    def save_db(self):
        """Sauvegarder la liste des utilisateurs shadow-ban"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.shadowbanned_users, f, indent=4)
        except Exception as e:
            print(f"⚠️ Erreur lors de la sauvegarde de la base de données: {str(e)}")
    
    def is_shadowbanned(self, user_id):
        """Vérifier si un utilisateur est shadow-ban"""
        return str(user_id) in self.shadowbanned_users
    
    def get_shadowban_mode(self, user_id):
        """Obtenir le mode de shadow ban d'un utilisateur"""
        if self.is_shadowbanned(user_id):
            return self.shadowbanned_users[str(user_id)].get("mode", "delete")
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Intercepter les messages des utilisateurs shadow-ban"""
        if message.author.bot or not message.guild:
            return
        
        user_id = str(message.author.id)
        
        # Vérifier si l'utilisateur est shadow-ban
        if self.is_shadowbanned(user_id):
            mode = self.get_shadowban_mode(user_id)
            
            # Enregistrer le message original pour les logs
            original_content = message.content
            
            # Supprimer immédiatement le message pour tous les modes
            # Cela garantit que personne d'autre ne voit le message
            try:
                # Supprimer le message original immédiatement
                await message.delete()
                print(f"🗑️ Message de l'utilisateur shadow-ban {message.author.name} supprimé: {original_content}")
            except Exception as e:
                print(f"⚠️ Erreur lors de la suppression du message: {str(e)}")
                # Si la suppression échoue, on ne continue pas
                return
            
            # Mode 1: Suppression simple (ne rien faire d'autre)
            if mode == "delete":
                pass
            
            # Mode 2: Remplacement par un message absurde
            elif mode == "modify":
                try:
                    # Créer un webhook pour imiter l'utilisateur
                    webhooks = await message.channel.webhooks()
                    webhook = None
                    
                    # Chercher un webhook existant ou en créer un nouveau
                    for wh in webhooks:
                        if wh.name == "ShadowBan System":
                            webhook = wh
                            break
                    
                    if webhook is None:
                        try:
                            webhook = await message.channel.create_webhook(name="ShadowBan System")
                        except Exception as e:
                            print(f"⚠️ Erreur lors de la création du webhook: {str(e)}")
                            return
                    
                    # Envoyer un message modifié via le webhook
                    nonsense = random.choice(self.nonsense_messages)
                    
                    # Envoyer le message modifié en imitant l'utilisateur
                    await webhook.send(
                        content=nonsense,
                        username=message.author.display_name,
                        avatar_url=message.author.display_avatar.url,
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                    
                    print(f"✏️ Message de l'utilisateur shadow-ban {message.author.name} remplacé: {original_content} -> {nonsense}")
                except Exception as e:
                    print(f"⚠️ Erreur lors du remplacement du message: {str(e)}")
            
            # Mode 3: Invisibilité totale (ne rien faire après la suppression)
            elif mode == "invisible":
                # Le message est déjà supprimé, on ne fait rien d'autre
                print(f"👻 Message de l'utilisateur shadow-ban {message.author.name} rendu invisible: {original_content}")
            
            # Envoyer une copie du message aux administrateurs
            await self.log_shadowban_message(message.author, message.channel, original_content)
    
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Intercepter les suppressions de messages pour les utilisateurs shadow-ban"""
        if message.author.bot or not message.guild:
            return
        
        user_id = str(message.author.id)
        
        # Vérifier si l'utilisateur est shadow-ban
        if self.is_shadowbanned(user_id):
            # Stocker le message supprimé dans le cache pour simuler qu'il est toujours visible pour l'utilisateur
            self.message_cache[message.id] = {
                "content": message.content,
                "author_id": user_id,
                "channel_id": message.channel.id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Supprimer les messages trop anciens du cache (plus de 1 heure)
            current_time = datetime.now()
            to_delete = []
            for msg_id, msg_data in self.message_cache.items():
                msg_time = datetime.fromisoformat(msg_data["timestamp"])
                if (current_time - msg_time).total_seconds() > 3600:  # 1 heure
                    to_delete.append(msg_id)
            
            for msg_id in to_delete:
                del self.message_cache[msg_id]
    
    async def log_shadowban_message(self, author, channel, content):
        """Envoyer une copie du message aux administrateurs"""
        try:
            # Trouver le canal d'alerte
            alert_channel = None
            if self.alert_channel_id:
                alert_channel = self.bot.get_channel(int(self.alert_channel_id))
            
            if alert_channel:
                embed = discord.Embed(
                    title="🥷 Message Shadow-Ban Intercepté",
                    description=f"Un message d'un utilisateur shadow-ban a été intercepté.",
                    color=discord.Color.dark_gray(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="Utilisateur",
                    value=f"{author.mention} ({author.name}, ID: {author.id})",
                    inline=False
                )
                
                embed.add_field(
                    name="Canal",
                    value=f"{channel.mention}",
                    inline=True
                )
                
                embed.add_field(
                    name="Mode",
                    value=f"{self.get_shadowban_mode(author.id)}",
                    inline=True
                )
                
                embed.add_field(
                    name="Contenu du message",
                    value=f"```{content[:1000]}```" if content else "*Aucun contenu textuel*",
                    inline=False
                )
                
                await alert_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi du log: {str(e)}")
    
    @commands.command(name="shadowban")
    @commands.has_permissions(administrator=True)
    async def shadowban_user(self, ctx, member: discord.Member, mode: str = "delete"):
        """Shadow-ban un utilisateur pour rendre ses messages invisibles
        
        Usage: !shadowban @utilisateur [delete|modify|invisible]
        
        Modes:
        - delete: Supprime les messages après envoi
        - modify: Remplace les messages par du texte absurde via webhook
        - invisible: Supprime les messages sans les remplacer
        """
        # Vérifier que le mode est valide
        if mode not in ["delete", "modify", "invisible"]:
            await ctx.send("⚠️ Mode invalide. Utilisez 'delete', 'modify' ou 'invisible'.")
            return
        
        # Vérifier qu'on ne shadow-ban pas un administrateur
        if member.guild_permissions.administrator and member.id != ctx.author.id:
            await ctx.send("⚠️ Impossible de shadow-ban un administrateur.")
            return
        
        # Vérifier les permissions pour le mode modify
        if mode == "modify":
            # Vérifier que le bot a les permissions nécessaires pour créer des webhooks
            if not ctx.guild.me.guild_permissions.manage_webhooks:
                await ctx.send("⚠️ Le bot n'a pas la permission de gérer les webhooks, nécessaire pour le mode 'modify'.")
                return
        
        # Ajouter l'utilisateur à la liste des shadow-ban
        self.shadowbanned_users[str(member.id)] = {
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "banned_by": ctx.author.id
        }
        
        # Sauvegarder la base de données
        self.save_db()
        
        # Confirmer l'action à l'administrateur
        await ctx.message.delete()  # Supprimer la commande pour être discret
        
        confirm_embed = discord.Embed(
            title="🥷 Shadow Ban Activé",
            description=f"L'utilisateur {member.mention} a été shadow-ban avec succès.",
            color=discord.Color.dark_gray()
        )
        
        confirm_embed.add_field(
            name="Mode",
            value=f"`{mode}`",
            inline=True
        )
        
        confirm_embed.add_field(
            name="Date",
            value=f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            inline=True
        )
        
        confirm_embed.set_footer(text="L'utilisateur ne sera pas notifié de cette action.")
        
        # Envoyer la confirmation en message privé à l'administrateur
        try:
            await ctx.author.send(embed=confirm_embed)
        except:
            # Si l'envoi en MP échoue, envoyer dans le canal mais supprimer après 5 secondes
            confirm_msg = await ctx.send(embed=confirm_embed)
            await asyncio.sleep(5)
            await confirm_msg.delete()
    
    @commands.command(name="unshadowban")
    @commands.has_permissions(administrator=True)
    async def unshadowban_user(self, ctx, member: discord.Member):
        """Retirer le shadow-ban d'un utilisateur
        
        Usage: !unshadowban @utilisateur
        """
        user_id = str(member.id)
        
        # Vérifier si l'utilisateur est shadow-ban
        if user_id not in self.shadowbanned_users:
            await ctx.send("⚠️ Cet utilisateur n'est pas shadow-ban.")
            return
        
        # Retirer l'utilisateur de la liste des shadow-ban
        del self.shadowbanned_users[user_id]
        
        # Sauvegarder la base de données
        self.save_db()
        
        # Confirmer l'action à l'administrateur
        await ctx.message.delete()  # Supprimer la commande pour être discret
        
        confirm_embed = discord.Embed(
            title="🥷 Shadow Ban Désactivé",
            description=f"L'utilisateur {member.mention} n'est plus shadow-ban.",
            color=discord.Color.green()
        )
        
        confirm_embed.add_field(
            name="Date",
            value=f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            inline=True
        )
        
        # Envoyer la confirmation en message privé à l'administrateur
        try:
            await ctx.author.send(embed=confirm_embed)
        except:
            # Si l'envoi en MP échoue, envoyer dans le canal mais supprimer après 5 secondes
            confirm_msg = await ctx.send(embed=confirm_embed)
            await asyncio.sleep(5)
            await confirm_msg.delete()
    
    @commands.command(name="shadowbanned")
    @commands.has_permissions(administrator=True)
    async def list_shadowbanned(self, ctx):
        """Lister tous les utilisateurs shadow-ban
        
        Usage: !shadowbanned
        """
        if not self.shadowbanned_users:
            await ctx.send("✅ Aucun utilisateur n'est actuellement shadow-ban.")
            return
        
        embed = discord.Embed(
            title="👻 Utilisateurs Shadow-Ban",
            description=f"Liste des {len(self.shadowbanned_users)} utilisateurs actuellement shadow-ban.",
            color=discord.Color.dark_gray()
        )
        
        for user_id, data in self.shadowbanned_users.items():
            try:
                member = ctx.guild.get_member(int(user_id))
                banned_by = ctx.guild.get_member(int(data.get("banned_by", 0)))
                
                if member:
                    embed.add_field(
                        name=f"{member.name} (ID: {user_id})",
                        value=f"**Mode:** {data.get('mode', 'delete')}\n"
                              f"**Date:** {datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())).strftime('%d/%m/%Y')}\n"
                              f"**Par:** {banned_by.mention if banned_by else 'Inconnu'}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"Utilisateur inconnu (ID: {user_id})",
                        value=f"**Mode:** {data.get('mode', 'delete')}\n"
                              f"**Date:** {datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())).strftime('%d/%m/%Y')}\n"
                              f"**Par:** {banned_by.mention if banned_by else 'Inconnu'}",
                        inline=False
                    )
            except Exception as e:
                print(f"⚠️ Erreur lors de l'affichage de l'utilisateur {user_id}: {str(e)}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="shadowban_mode")
    @commands.has_permissions(administrator=True)
    async def change_shadowban_mode(self, ctx, member: discord.Member, mode: str):
        """Changer le mode de shadow-ban d'un utilisateur
        
        Usage: !shadowban_mode @utilisateur [delete|modify|invisible]
        
        Modes:
        - delete: Supprime les messages après envoi
        - modify: Remplace les messages par du texte absurde via webhook
        - invisible: Supprime les messages sans les remplacer
        """
        user_id = str(member.id)
        
        # Vérifier si l'utilisateur est shadow-ban
        if user_id not in self.shadowbanned_users:
            await ctx.send("⚠️ Cet utilisateur n'est pas shadow-ban.")
            return
        
        # Vérifier que le mode est valide
        if mode not in ["delete", "modify", "invisible"]:
            await ctx.send("⚠️ Mode invalide. Utilisez 'delete', 'modify' ou 'invisible'.")
            return
        
        # Vérifier les permissions pour le mode modify
        if mode == "modify":
            # Vérifier que le bot a les permissions nécessaires pour créer des webhooks
            if not ctx.guild.me.guild_permissions.manage_webhooks:
                await ctx.send("⚠️ Le bot n'a pas la permission de gérer les webhooks, nécessaire pour le mode 'modify'.")
                return
        
        # Mettre à jour le mode
        self.shadowbanned_users[user_id]["mode"] = mode
        
        # Sauvegarder la base de données
        self.save_db()
        
        # Confirmer l'action à l'administrateur
        await ctx.message.delete()  # Supprimer la commande pour être discret
        
        confirm_embed = discord.Embed(
            title="🥷 Mode Shadow Ban Modifié",
            description=f"Le mode de shadow-ban de {member.mention} a été changé.",
            color=discord.Color.dark_gray()
        )
        
        confirm_embed.add_field(
            name="Nouveau Mode",
            value=f"`{mode}`",
            inline=True
        )
        
        # Envoyer la confirmation en message privé à l'administrateur
        try:
            await ctx.author.send(embed=confirm_embed)
        except:
            # Si l'envoi en MP échoue, envoyer dans le canal mais supprimer après 5 secondes
            confirm_msg = await ctx.send(embed=confirm_embed)
            await asyncio.sleep(5)
            await confirm_msg.delete()
    
    @commands.command(name="clean_webhooks")
    @commands.has_permissions(administrator=True)
    async def clean_webhooks(self, ctx):
        """Nettoyer les webhooks créés par le système de shadow ban
        
        Usage: !clean_webhooks
        """
        count = 0
        for channel in ctx.guild.text_channels:
            try:
                webhooks = await channel.webhooks()
                for webhook in webhooks:
                    if webhook.name == "ShadowBan System":
                        await webhook.delete(reason="Nettoyage des webhooks de shadow ban")
                        count += 1
            except Exception as e:
                print(f"⚠️ Erreur lors du nettoyage des webhooks dans {channel.name}: {str(e)}")
        
        await ctx.send(f"✅ {count} webhooks de shadow ban ont été supprimés.")
    
    @commands.command(name="shadowban_help")
    @commands.has_permissions(administrator=True)
    async def shadowban_help(self, ctx):
        """Afficher l'aide du système de shadow ban
        
        Usage: !shadowban_help
        """
        embed = discord.Embed(
            title="🥷 Aide du Système de Shadow Ban",
            description="Le système de shadow ban permet de rendre un utilisateur invisible sans qu'il le sache.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Modes disponibles",
            value="• `delete` : Supprime les messages après envoi\n"
                  "• `modify` : Remplace les messages par du texte absurde via webhook\n"
                  "• `invisible` : Supprime les messages sans les remplacer",
            inline=False
        )
        
        embed.add_field(
            name="Commandes",
            value="• `!shadowban @utilisateur [mode]` : Shadow-ban un utilisateur\n"
                  "• `!unshadowban @utilisateur` : Retirer le shadow-ban d'un utilisateur\n"
                  "• `!shadowbanned` : Lister tous les utilisateurs shadow-ban\n"
                  "• `!shadowban_mode @utilisateur mode` : Changer le mode de shadow-ban\n"
                  "• `!clean_webhooks` : Nettoyer les webhooks créés par le système",
            inline=False
        )
        
        embed.add_field(
            name="Remarques",
            value="• Le mode `modify` nécessite la permission de gérer les webhooks\n"
                  "• Les administrateurs ne peuvent pas être shadow-ban\n"
                  "• Les commandes de shadow ban sont automatiquement supprimées\n"
                  "• Les confirmations sont envoyées en message privé",
            inline=False
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ShadowBan(bot)) 