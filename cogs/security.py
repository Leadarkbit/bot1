import discord
from discord.ext import commands
import os
import json
import secrets
import string
import asyncio
import ipaddress
from datetime import datetime, timedelta
import config  # Importer le fichier de configuration

class Security(commands.Cog):
    """Système de sécurité avec authentification par clé secrète en cas de changement d'IP"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "data/security_db.json"
        self.user_data = {}
        self.verification_in_progress = set()
        self.max_attempts = config.MAX_VERIFICATION_ATTEMPTS
        self.failed_attempts = {}
        self.special_role_id = config.SPECIAL_ROLE_ID  # ID du rôle spécial à gérer
        self.member_role_id = config.MEMBER_ROLE_ID  # ID du rôle Membre
        self.pending_verifications = {}  # {user_id: {guild_id, key}}
        
        # Créer le dossier data s'il n'existe pas
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        
        # Charger la base de données
        self.load_db()
        
        print("🔒 Module de sécurité initialisé avec succès!")
        print(f"🔑 Rôle spécial configuré: {self.special_role_id}")
        print(f"🔑 Rôle membre configuré: {self.member_role_id}")
    
    def load_db(self):
        """Charger la base de données des utilisateurs"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r') as f:
                    self.user_data = json.load(f)
                print(f"✅ Base de données de sécurité chargée: {len(self.user_data)} utilisateurs")
            else:
                self.user_data = {}
                self.save_db()
                print("✅ Nouvelle base de données de sécurité créée")
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement de la base de données: {str(e)}")
            self.user_data = {}
    
    def save_db(self):
        """Sauvegarder la base de données des utilisateurs"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.user_data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Erreur lors de la sauvegarde de la base de données: {str(e)}")
    
    def generate_secret_key(self, length=8):
        """Générer une clé secrète aléatoire"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def get_user_ip(self, member):
        """Simuler l'obtention de l'IP d'un utilisateur (à remplacer par votre méthode)"""
        # Note: Discord ne fournit pas l'IP des utilisateurs via l'API
        # Cette fonction est un placeholder - dans un environnement réel,
        # vous devriez utiliser une autre méthode pour obtenir l'IP
        
        # Pour les tests, on génère une IP aléatoire basée sur l'ID de l'utilisateur
        # NE PAS UTILISER EN PRODUCTION
        user_id_int = int(member.id)
        ip_parts = [
            (user_id_int >> 24) & 0xFF,
            (user_id_int >> 16) & 0xFF,
            (user_id_int >> 8) & 0xFF,
            user_id_int & 0xFF
        ]
        return f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{ip_parts[3]}"
    
    async def send_secret_key(self, member, key, is_new_member=False):
        """Envoyer la clé secrète à l'utilisateur en message privé"""
        try:
            embed = discord.Embed(
                title="🔐 Clé de Sécurité",
                description="Bienvenue sur le serveur! Pour votre sécurité, nous avons généré une clé unique.",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Votre Clé Secrète",
                value=f"`{key}`",
                inline=False
            )
            
            if is_new_member:
                embed.add_field(
                    name="⚠️ Action Requise",
                    value="Pour accéder au serveur, vous devez utiliser cette clé.\n"
                          "Tapez `!verify [votre clé]` dans n'importe quel canal du serveur.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Important",
                    value="Conservez cette clé en lieu sûr. Elle vous sera demandée si nous détectons "
                          "un changement d'IP ou une connexion depuis un nouvel appareil.",
                    inline=False
                )
            
            await member.send(embed=embed)
            return True
        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi de la clé secrète à {member.name}: {str(e)}")
            return False
    
    async def lock_user(self, member, guild):
        """Retirer les rôles d'un utilisateur et lui attribuer un rôle de vérification"""
        try:
            # Sauvegarder les rôles actuels
            user_id = str(member.id)
            if user_id in self.user_data:
                self.user_data[user_id]["previous_roles"] = [role.id for role in member.roles if role.id != guild.id]
            
            # Vérifier si l'utilisateur a le rôle spécial
            special_role = guild.get_role(self.special_role_id)
            has_special_role = special_role in member.roles
            
            # Sauvegarder cette information
            if user_id in self.user_data:
                self.user_data[user_id]["had_special_role"] = has_special_role
                self.save_db()
            
            # Créer ou obtenir le rôle de vérification
            verification_role = discord.utils.get(guild.roles, name="En Vérification")
            if not verification_role:
                try:
                    verification_role = await guild.create_role(
                        name="En Vérification",
                        color=discord.Color.orange(),
                        reason="Rôle pour les utilisateurs en attente de vérification"
                    )
                    
                    # Configurer les permissions pour ce rôle
                    for channel in guild.channels:
                        if isinstance(channel, discord.TextChannel):
                            # Autoriser uniquement le canal de vérification
                            if channel.name == "verification":
                                await channel.set_permissions(verification_role, read_messages=True, send_messages=True)
                            else:
                                await channel.set_permissions(verification_role, read_messages=False)
                except Exception as e:
                    print(f"⚠️ Erreur lors de la création du rôle de vérification: {str(e)}")
                    return False
            
            # Retirer tous les rôles existants
            roles_to_remove = [role for role in member.roles if role.id != guild.id and role != verification_role]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Vérification de sécurité - Changement d'IP détecté")
            
            # Ajouter le rôle de vérification
            await member.add_roles(verification_role, reason="Vérification de sécurité requise")
            
            # Journaliser l'action
            if has_special_role:
                print(f"🔒 Rôle spécial {self.special_role_id} retiré de {member.name} pendant la vérification")
            
            return True
        except Exception as e:
            print(f"⚠️ Erreur lors du verrouillage de l'utilisateur {member.name}: {str(e)}")
            return False
    
    async def unlock_user(self, member, guild):
        """Restaurer les rôles d'un utilisateur après vérification réussie"""
        try:
            user_id = str(member.id)
            
            # Obtenir le rôle de vérification
            verification_role = discord.utils.get(guild.roles, name="En Vérification")
            
            # Retirer le rôle de vérification
            if verification_role and verification_role in member.roles:
                await member.remove_roles(verification_role, reason="Vérification de sécurité réussie")
            
            # Restaurer les rôles précédents
            if user_id in self.user_data and "previous_roles" in self.user_data[user_id]:
                roles_to_add = []
                for role_id in self.user_data[user_id]["previous_roles"]:
                    role = guild.get_role(role_id)
                    if role:
                        roles_to_add.append(role)
                
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason="Vérification de sécurité réussie")
            
            # Vérifier si l'utilisateur avait le rôle spécial avant la vérification
            had_special_role = False
            if user_id in self.user_data and "had_special_role" in self.user_data[user_id]:
                had_special_role = self.user_data[user_id]["had_special_role"]
            
            # Si l'utilisateur avait le rôle spécial, s'assurer qu'il est restauré
            if had_special_role:
                special_role = guild.get_role(self.special_role_id)
                if special_role and special_role not in member.roles:
                    await member.add_roles(special_role, reason="Restauration du rôle spécial après vérification")
                    print(f"✅ Rôle spécial {self.special_role_id} restauré pour {member.name} après vérification")
            
            # Mettre à jour l'IP dans la base de données
            if user_id in self.user_data:
                self.user_data[user_id]["ip"] = self.get_user_ip(member)
                self.user_data[user_id]["last_verified"] = datetime.now().isoformat()
                self.save_db()
            
            return True
        except Exception as e:
            print(f"⚠️ Erreur lors du déverrouillage de l'utilisateur {member.name}: {str(e)}")
            return False
    
    async def start_verification(self, member, guild):
        """Démarrer le processus de vérification pour un utilisateur"""
        user_id = str(member.id)
        
        # Vérifier si une vérification est déjà en cours
        if user_id in self.verification_in_progress:
            return
        
        self.verification_in_progress.add(user_id)
        
        try:
            # Vérifier si l'utilisateur a le rôle spécial avant de le verrouiller
            special_role = guild.get_role(self.special_role_id)
            has_special_role = special_role in member.roles
            
            # Verrouiller l'utilisateur
            await self.lock_user(member, guild)
            
            # Envoyer un message de vérification
            embed = discord.Embed(
                title="🔒 Vérification de Sécurité Requise",
                description="Nous avons détecté un changement d'IP pour votre compte.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="Instructions",
                value="Pour retrouver l'accès au serveur, veuillez entrer la clé secrète "
                      "qui vous a été envoyée lors de votre arrivée sur le serveur.\n\n"
                      "Répondez à ce message avec votre clé dans les 10 minutes.",
                inline=False
            )
            
            if has_special_role:
                embed.add_field(
                    name="Note",
                    value=f"Votre rôle spécial a été temporairement retiré et sera restauré après vérification.",
                    inline=False
                )
            
            verification_message = await member.send(embed=embed)
            
            # Attendre la réponse de l'utilisateur
            def check(m):
                return m.author.id == member.id and m.channel.id == verification_message.channel.id
            
            try:
                response = await self.bot.wait_for('message', check=check, timeout=600)  # 10 minutes
                
                # Vérifier la clé
                if user_id in self.user_data and response.content == self.user_data[user_id]["secret_key"]:
                    # Clé correcte
                    success_embed = discord.Embed(
                        title="✅ Vérification Réussie",
                        description="Votre identité a été vérifiée avec succès. Vos accès au serveur ont été restaurés.",
                        color=discord.Color.green()
                    )
                    
                    if has_special_role:
                        success_embed.add_field(
                            name="Rôle Spécial",
                            value="Votre rôle spécial a été restauré.",
                            inline=False
                        )
                    
                    await member.send(embed=success_embed)
                    
                    # Restaurer les accès
                    await self.unlock_user(member, guild)
                    
                    # Réinitialiser les tentatives échouées
                    if user_id in self.failed_attempts:
                        del self.failed_attempts[user_id]
                else:
                    # Clé incorrecte
                    failure_embed = discord.Embed(
                        title="❌ Vérification Échouée",
                        description="La clé que vous avez fournie est incorrecte.",
                        color=discord.Color.red()
                    )
                    
                    # Gérer les tentatives échouées
                    if user_id not in self.failed_attempts:
                        self.failed_attempts[user_id] = 1
                    else:
                        self.failed_attempts[user_id] += 1
                    
                    attempts_left = self.max_attempts - self.failed_attempts[user_id]
                    
                    if attempts_left > 0:
                        failure_embed.add_field(
                            name="Tentatives restantes",
                            value=f"Il vous reste {attempts_left} tentative(s).\n"
                                  f"Vous pouvez réessayer en envoyant votre clé.",
                            inline=False
                        )
                        await member.send(embed=failure_embed)
                        
                        # Relancer la vérification
                        self.verification_in_progress.remove(user_id)
                        await self.start_verification(member, guild)
                        return
                    else:
                        # Trop de tentatives échouées
                        failure_embed.add_field(
                            name="Compte verrouillé",
                            value="Vous avez dépassé le nombre maximum de tentatives.\n"
                                  "Veuillez contacter un administrateur pour assistance.",
                            inline=False
                        )
                        await member.send(embed=failure_embed)
                        
                        # Alerter les administrateurs
                        await self.alert_admins(member, guild, "tentatives_max")
            except asyncio.TimeoutError:
                # L'utilisateur n'a pas répondu à temps
                timeout_embed = discord.Embed(
                    title="⏰ Délai Expiré",
                    description="Vous n'avez pas fourni votre clé dans le délai imparti.",
                    color=discord.Color.red()
                )
                
                timeout_embed.add_field(
                    name="Que faire maintenant?",
                    value="Veuillez contacter un administrateur pour assistance.",
                    inline=False
                )
                
                await member.send(embed=timeout_embed)
                
                # Alerter les administrateurs
                await self.alert_admins(member, guild, "timeout")
        except Exception as e:
            print(f"⚠️ Erreur lors de la vérification de {member.name}: {str(e)}")
        finally:
            # Retirer l'utilisateur de la liste des vérifications en cours
            if user_id in self.verification_in_progress:
                self.verification_in_progress.remove(user_id)
    
    async def alert_admins(self, member, guild, reason):
        """Alerter les administrateurs d'un problème de sécurité"""
        try:
            # Trouver le canal d'alerte
            alert_channel_id = config.SECURITY_LOG_CHANNEL_ID
            if alert_channel_id:
                alert_channel = self.bot.get_channel(int(alert_channel_id))
            else:
                # Chercher un canal de logs ou créer un canal d'alerte
                alert_channel = discord.utils.get(guild.text_channels, name="security-alerts")
                if not alert_channel:
                    # Chercher la catégorie admin ou logs
                    admin_category = discord.utils.get(guild.categories, name="Administration")
                    if not admin_category:
                        admin_category = discord.utils.get(guild.categories, name="Logs")
                    
                    # Créer le canal d'alerte
                    alert_channel = await guild.create_text_channel(
                        name="security-alerts",
                        category=admin_category,
                        topic="Alertes de sécurité automatiques",
                        reason="Canal pour les alertes de sécurité"
                    )
                    
                    # Configurer les permissions pour que seuls les admins puissent voir ce canal
                    await alert_channel.set_permissions(guild.default_role, read_messages=False)
                    admin_role = discord.utils.get(guild.roles, name="Admin")
                    if admin_role:
                        await alert_channel.set_permissions(admin_role, read_messages=True, send_messages=True)
            
            if alert_channel:
                # Créer l'embed d'alerte
                alert_embed = discord.Embed(
                    title="🚨 Alerte de Sécurité",
                    description=f"Problème de sécurité détecté pour l'utilisateur {member.mention}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                # Ajouter les détails selon la raison
                if reason == "ip_change":
                    user_id = str(member.id)
                    old_ip = self.user_data[user_id]["ip"] if user_id in self.user_data else "Inconnue"
                    new_ip = self.get_user_ip(member)
                    
                    alert_embed.add_field(
                        name="Type d'alerte",
                        value="Changement d'IP détecté",
                        inline=False
                    )
                    
                    alert_embed.add_field(
                        name="Ancienne IP",
                        value=f"`{old_ip}`",
                        inline=True
                    )
                    
                    alert_embed.add_field(
                        name="Nouvelle IP",
                        value=f"`{new_ip}`",
                        inline=True
                    )
                elif reason == "tentatives_max":
                    alert_embed.add_field(
                        name="Type d'alerte",
                        value="Nombre maximum de tentatives de vérification atteint",
                        inline=False
                    )
                elif reason == "timeout":
                    alert_embed.add_field(
                        name="Type d'alerte",
                        value="L'utilisateur n'a pas répondu à la demande de vérification",
                        inline=False
                    )
                
                alert_embed.add_field(
                    name="Utilisateur",
                    value=f"**Nom:** {member.name}\n**ID:** {member.id}\n**Créé le:** {member.created_at.strftime('%d/%m/%Y')}\n**Rejoint le:** {member.joined_at.strftime('%d/%m/%Y')}",
                    inline=False
                )
                
                alert_embed.add_field(
                    name="Actions possibles",
                    value="• `/verify @utilisateur` - Forcer la vérification de l'utilisateur\n"
                          "• `/unlock @utilisateur` - Restaurer les accès de l'utilisateur\n"
                          "• `/ban @utilisateur` - Bannir l'utilisateur du serveur",
                    inline=False
                )
                
                # Mentionner les administrateurs
                await alert_channel.send(content="@here", embed=alert_embed)
        except Exception as e:
            print(f"⚠️ Erreur lors de l'alerte des administrateurs: {str(e)}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Gérer l'arrivée d'un nouveau membre"""
        user_id = str(member.id)
        
        # Générer une clé secrète
        secret_key = self.generate_secret_key()
        
        # Obtenir l'IP de l'utilisateur
        ip = self.get_user_ip(member)
        
        # Stocker les informations dans la base de données
        self.user_data[user_id] = {
            "secret_key": secret_key,
            "ip": ip,
            "joined_at": datetime.now().isoformat(),
            "last_verified": None,  # Pas encore vérifié
            "verified": False  # Nouveau membre, pas encore vérifié
        }
        
        # Sauvegarder la base de données
        self.save_db()
        
        # Ajouter à la liste des vérifications en attente
        self.pending_verifications[user_id] = {
            "guild_id": member.guild.id,
            "key": secret_key
        }
        
        # Envoyer la clé secrète à l'utilisateur
        success = await self.send_secret_key(member, secret_key, is_new_member=True)
        
        if success:
            print(f"🔑 Clé de vérification envoyée à {member.name} ({member.id})")
            
            # Envoyer un message dans le canal de bienvenue si configuré
            welcome_channel_id = config.WELCOME_CHANNEL_ID
            if welcome_channel_id:
                try:
                    welcome_channel = member.guild.get_channel(int(welcome_channel_id))
                    if welcome_channel:
                        embed = discord.Embed(
                            title="👋 Nouveau Membre",
                            description=f"Bienvenue {member.mention} sur le serveur!",
                            color=discord.Color.green()
                        )
                        embed.add_field(
                            name="Vérification Requise",
                            value="Une clé de sécurité a été envoyée en message privé.\n"
                                  "Utilisez `!verify [votre clé]` pour accéder au serveur.",
                            inline=False
                        )
                        await welcome_channel.send(embed=embed)
                except Exception as e:
                    print(f"⚠️ Erreur lors de l'envoi du message de bienvenue: {str(e)}")
        else:
            print(f"⚠️ Impossible d'envoyer la clé de vérification à {member.name} ({member.id})")
            
            # Alerter les administrateurs
            await self.alert_admins(member, member.guild, "dm_closed")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Vérifier l'IP de l'utilisateur à chaque message et traiter les commandes de vérification"""
        # Ignorer les messages des bots et les messages privés
        if message.author.bot or not message.guild:
            return
        
        user_id = str(message.author.id)
        
        # Vérifier si c'est une commande de vérification
        if message.content.startswith('!verify '):
            await self.process_verification(message)
            return
        
        # Vérifier si l'utilisateur est dans la base de données
        if user_id not in self.user_data:
            # Nouvel utilisateur, l'ajouter à la base de données
            await self.on_member_join(message.author)
            return
        
        # Vérifier si l'utilisateur est déjà en cours de vérification
        if user_id in self.verification_in_progress:
            return
        
        # Vérifier si l'utilisateur n'est pas encore vérifié
        if not self.user_data[user_id].get("verified", False):
            # Rappeler à l'utilisateur qu'il doit se vérifier
            if user_id in self.pending_verifications:
                # Ne pas spammer le rappel, vérifier si on l'a déjà fait récemment
                last_reminder = self.user_data[user_id].get("last_reminder")
                if not last_reminder or (datetime.now() - datetime.fromisoformat(last_reminder)).total_seconds() > 300:  # 5 minutes
                    await message.channel.send(
                        f"{message.author.mention}, vous devez vous vérifier pour accéder pleinement au serveur. "
                        f"Utilisez `!verify [votre clé]` avec la clé qui vous a été envoyée en message privé.",
                        delete_after=10
                    )
                    self.user_data[user_id]["last_reminder"] = datetime.now().isoformat()
                    self.save_db()
            return
        
        # Obtenir l'IP actuelle
        current_ip = self.get_user_ip(message.author)
        
        # Vérifier si l'IP a changé
        if current_ip != self.user_data[user_id]["ip"]:
            print(f"🔍 Changement d'IP détecté pour {message.author.name}: {self.user_data[user_id]['ip']} -> {current_ip}")
            
            # Alerter les administrateurs
            await self.alert_admins(message.author, message.guild, "ip_change")
            
            # Démarrer le processus de vérification
            await self.start_verification(message.author, message.guild)
    
    async def process_verification(self, message):
        """Traiter une commande de vérification"""
        user_id = str(message.author.id)
        
        # Supprimer le message pour la confidentialité
        try:
            await message.delete()
        except:
            pass
        
        # Extraire la clé
        parts = message.content.split(' ', 1)
        if len(parts) < 2:
            await message.channel.send(
                f"{message.author.mention}, format incorrect. Utilisez `!verify [votre clé]`.",
                delete_after=5
            )
            return
        
        provided_key = parts[1].strip()
        
        # Vérifier si l'utilisateur est en attente de vérification
        if user_id in self.pending_verifications:
            expected_key = self.pending_verifications[user_id]["key"]
            
            if provided_key == expected_key:
                # Clé correcte
                guild = message.guild
                
                # Marquer comme vérifié
                self.user_data[user_id]["verified"] = True
                self.user_data[user_id]["last_verified"] = datetime.now().isoformat()
                self.save_db()
                
                # Retirer de la liste des vérifications en attente
                del self.pending_verifications[user_id]
                
                # Attribuer le rôle Membre si configuré
                if self.member_role_id:
                    try:
                        member_role = guild.get_role(int(self.member_role_id))
                        if member_role:
                            await message.author.add_roles(member_role, reason="Vérification réussie")
                            print(f"✅ Rôle Membre attribué à {message.author.name}")
                    except Exception as e:
                        print(f"⚠️ Erreur lors de l'attribution du rôle Membre: {str(e)}")
                
                # Confirmer la vérification
                embed = discord.Embed(
                    title="✅ Vérification Réussie",
                    description=f"{message.author.mention}, votre compte a été vérifié avec succès!",
                    color=discord.Color.green()
                )
                
                await message.channel.send(embed=embed, delete_after=10)
                
                # Envoyer un message privé de confirmation
                try:
                    confirm_embed = discord.Embed(
                        title="✅ Vérification Réussie",
                        description="Votre compte a été vérifié avec succès! Vous avez maintenant accès à tous les canaux du serveur.",
                        color=discord.Color.green()
                    )
                    await message.author.send(embed=confirm_embed)
                except:
                    pass
                
                print(f"✅ Utilisateur {message.author.name} vérifié avec succès")
            else:
                # Clé incorrecte
                # Incrémenter le compteur d'échecs
                if user_id not in self.failed_attempts:
                    self.failed_attempts[user_id] = 1
                else:
                    self.failed_attempts[user_id] += 1
                
                # Informer l'utilisateur
                await message.channel.send(
                    f"{message.author.mention}, clé incorrecte. Vérifiez votre message privé et réessayez. "
                    f"Tentative {self.failed_attempts[user_id]}/{self.max_attempts}.",
                    delete_after=5
                )
                
                # Si trop d'échecs, alerter les administrateurs
                if self.failed_attempts[user_id] >= self.max_attempts:
                    await self.alert_admins(message.author, message.guild, "verification_failed")
                    self.failed_attempts[user_id] = 0  # Réinitialiser pour permettre de réessayer
        else:
            # L'utilisateur n'est pas en attente de vérification
            if user_id in self.user_data and self.user_data[user_id].get("verified", False):
                await message.channel.send(
                    f"{message.author.mention}, votre compte est déjà vérifié.",
                    delete_after=5
                )
            else:
                await message.channel.send(
                    f"{message.author.mention}, aucune vérification en attente. Contactez un administrateur si vous avez besoin d'aide.",
                    delete_after=5
                )
    
    @commands.command(name="set_member_role")
    @commands.has_permissions(administrator=True)
    async def set_member_role(self, ctx, role: discord.Role = None):
        """Définir le rôle à attribuer aux membres vérifiés
        
        Usage: !set_member_role @rôle
        """
        if role:
            # Mettre à jour le rôle dans la configuration
            config.MEMBER_ROLE_ID = role.id
            self.member_role_id = role.id
            
            await ctx.send(f"✅ Le rôle {role.mention} sera désormais attribué aux membres vérifiés.")
        else:
            # Afficher le rôle actuel
            if self.member_role_id:
                role = ctx.guild.get_role(int(self.member_role_id))
                if role:
                    await ctx.send(f"ℹ️ Le rôle actuel pour les membres vérifiés est: {role.mention}")
                else:
                    await ctx.send("⚠️ Le rôle configuré n'existe pas ou n'est pas accessible.")
            else:
                await ctx.send("ℹ️ Aucun rôle n'est configuré pour les membres vérifiés.")
    
    @commands.command(name="admin_verify")
    @commands.has_permissions(administrator=True)
    async def force_verify(self, ctx, member: discord.Member):
        """Forcer la vérification d'un utilisateur (Admin uniquement)
        
        Usage: !admin_verify @utilisateur
        """
        user_id = str(member.id)
        
        # Marquer comme vérifié
        if user_id in self.user_data:
            self.user_data[user_id]["verified"] = True
            self.user_data[user_id]["last_verified"] = datetime.now().isoformat()
        else:
            # Nouvel utilisateur
            self.user_data[user_id] = {
                "secret_key": self.generate_secret_key(),
                "ip": self.get_user_ip(member),
                "joined_at": datetime.now().isoformat(),
                "last_verified": datetime.now().isoformat(),
                "verified": True
            }
        
        self.save_db()
        
        # Retirer de la liste des vérifications en attente
        if user_id in self.pending_verifications:
            del self.pending_verifications[user_id]
        
        # Attribuer le rôle Membre si configuré
        if self.member_role_id:
            try:
                member_role = ctx.guild.get_role(int(self.member_role_id))
                if member_role and member_role not in member.roles:
                    await member.add_roles(member_role, reason="Vérification forcée par administrateur")
                    print(f"✅ Rôle Membre attribué à {member.name} par administrateur")
            except Exception as e:
                print(f"⚠️ Erreur lors de l'attribution du rôle Membre: {str(e)}")
        
        await ctx.send(f"✅ {member.mention} a été vérifié avec succès par un administrateur.")
    
    @commands.command(name="unlock")
    @commands.has_permissions(administrator=True)
    async def force_unlock(self, ctx, member: discord.Member):
        """Restaurer les accès d'un utilisateur sans vérification (Admin uniquement)
        
        Usage: !unlock @utilisateur
        """
        user_id = str(member.id)
        
        # Mettre à jour l'IP dans la base de données
        if user_id in self.user_data:
            self.user_data[user_id]["ip"] = self.get_user_ip(member)
            self.user_data[user_id]["last_verified"] = datetime.now().isoformat()
            self.user_data[user_id]["verified"] = True
            self.save_db()
        
        # Déverrouiller l'utilisateur
        success = await self.unlock_user(member, ctx.guild)
        
        if success:
            await ctx.send(f"✅ Les accès de {member.mention} ont été restaurés.")
        else:
            await ctx.send(f"❌ Erreur lors de la restauration des accès de {member.mention}.")
    
    @commands.command(name="reset_key")
    @commands.has_permissions(administrator=True)
    async def reset_secret_key(self, ctx, member: discord.Member):
        """Réinitialiser la clé secrète d'un utilisateur (Admin uniquement)
        
        Usage: !reset_key @utilisateur
        """
        user_id = str(member.id)
        
        # Générer une nouvelle clé
        new_key = self.generate_secret_key()
        
        # Mettre à jour la base de données
        if user_id in self.user_data:
            self.user_data[user_id]["secret_key"] = new_key
            self.save_db()
        else:
            # Nouvel utilisateur
            self.user_data[user_id] = {
                "secret_key": new_key,
                "ip": self.get_user_ip(member),
                "joined_at": datetime.now().isoformat(),
                "last_verified": None,
                "verified": False
            }
            self.save_db()
        
        # Ajouter à la liste des vérifications en attente
        self.pending_verifications[user_id] = {
            "guild_id": ctx.guild.id,
            "key": new_key
        }
        
        # Envoyer la nouvelle clé à l'utilisateur
        success = await self.send_secret_key(member, new_key, is_new_member=True)
        
        if success:
            await ctx.send(f"✅ Une nouvelle clé a été générée et envoyée à {member.mention}.")
        else:
            await ctx.send(f"⚠️ La clé a été générée mais n'a pas pu être envoyée à {member.mention}.")
            
            # Envoyer la clé à l'administrateur
            admin_embed = discord.Embed(
                title="🔑 Nouvelle Clé Secrète",
                description=f"Voici la nouvelle clé pour {member.mention}:",
                color=discord.Color.blue()
            )
            
            admin_embed.add_field(
                name="Clé",
                value=f"`{new_key}`",
                inline=False
            )
            
            admin_embed.add_field(
                name="Instructions",
                value="Veuillez transmettre cette clé à l'utilisateur de manière sécurisée.",
                inline=False
            )
            
            await ctx.author.send(embed=admin_embed)
    
    @commands.command(name="security_help")
    async def security_help(self, ctx):
        """Afficher l'aide du système de sécurité
        
        Usage: !security_help
        """
        embed = discord.Embed(
            title="🔒 Aide du Système de Sécurité",
            description="Le système de sécurité protège le serveur en vérifiant l'identité des membres.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Pour les Membres",
            value="• `!verify [clé]` : Vérifier votre compte avec la clé reçue en message privé\n",
            inline=False
        )
        
        embed.add_field(
            name="Pour les Administrateurs",
            value="• `!admin_verify @utilisateur` : Forcer la vérification d'un utilisateur\n"
                  "• `!unlock @utilisateur` : Restaurer les accès d'un utilisateur\n"
                  "• `!reset_key @utilisateur` : Réinitialiser la clé secrète d'un utilisateur\n"
                  "• `!set_member_role @rôle` : Définir le rôle à attribuer aux membres vérifiés\n"
                  "• `!security_status` : Afficher les statistiques du système de sécurité",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="security_status")
    @commands.has_permissions(administrator=True)
    async def security_status(self, ctx):
        """Afficher l'état du système de sécurité (Admin uniquement)
        
        Usage: !security_status
        """
        embed = discord.Embed(
            title="🛡️ État du Système de Sécurité",
            description="Informations sur le système de sécurité par clé secrète",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Utilisateurs enregistrés",
            value=str(len(self.user_data)),
            inline=True
        )
        
        embed.add_field(
            name="Vérifications en cours",
            value=str(len(self.verification_in_progress)),
            inline=True
        )
        
        embed.add_field(
            name="Tentatives échouées",
            value=str(len(self.failed_attempts)),
            inline=True
        )
        
        # Ajouter les 5 derniers utilisateurs enregistrés
        recent_users = []
        for user_id, data in sorted(self.user_data.items(), key=lambda x: x[1].get("joined_at", ""), reverse=True)[:5]:
            user = ctx.guild.get_member(int(user_id))
            if user:
                joined_at = datetime.fromisoformat(data.get("joined_at", datetime.now().isoformat()))
                recent_users.append(f"• {user.mention} - {joined_at.strftime('%d/%m/%Y %H:%M')}")
        
        if recent_users:
            embed.add_field(
                name="Derniers utilisateurs enregistrés",
                value="\n".join(recent_users),
                inline=False
            )
        
        # Ajouter les utilisateurs en vérification
        if self.verification_in_progress:
            in_verification = []
            for user_id in self.verification_in_progress:
                user = ctx.guild.get_member(int(user_id))
                if user:
                    in_verification.append(f"• {user.mention}")
            
            if in_verification:
                embed.add_field(
                    name="Utilisateurs en vérification",
                    value="\n".join(in_verification),
                    inline=False
                )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Security(bot)) 