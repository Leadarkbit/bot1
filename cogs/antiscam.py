import os
import json
import discord
import random
import asyncio
import re
from datetime import datetime
from discord.ext import commands
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

class AntiScam(commands.Cog):
    """Système anti-arnaque avec mode humiliation pour détecter et troller les scammeurs"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "data/antiscam_db.json"
        self.scammer_data = {}  # {user_id: {count: int, last_scam: datetime, warnings: int}}
        
        # Récupérer les IDs de canaux depuis config.py ou les variables d'environnement
        if config and hasattr(config, 'SECURITY_LOG_CHANNEL_ID'):
            self.alert_channel_id = config.SECURITY_LOG_CHANNEL_ID
            print("📢 Canal d'alerte chargé depuis config.py")
        else:
            self.alert_channel_id = os.getenv('SECURITY_LOG_CHANNEL_ID')
            print("📢 Canal d'alerte chargé depuis les variables d'environnement")
            
        # Récupérer l'ID du rôle scammer
        if config and hasattr(config, 'SCAMMER_ROLE_ID'):
            self.scammer_role_id = config.SCAMMER_ROLE_ID
            print("🎭 Rôle scammer chargé depuis config.py")
        else:
            self.scammer_role_id = os.getenv('SCAMMER_ROLE_ID')
            print("🎭 Rôle scammer chargé depuis les variables d'environnement")
        
        # Mots-clés à haut risque (un seul suffit pour déclencher la détection)
        self.high_risk_keywords = [
            # Termes financiers à haut risque
            "paypal", "boursorama", "revolut", "binance", "coinbase", "n26", "wise", 
            "lydia", "paysafecard", "western union", "moneygram", "cashapp",
            "euro", "euros", "€", "$", "argent", "sous", "fric", "thune", "pognon",
            "banque", "carte bancaire", "virement", "transfert", "paiement",
            
            # Termes de parrainage
            "parrainage", "parrain", "filleul", "code promo", "code parrainage",
            "utilise mon code", "utilise mon lien", "inscris-toi avec mon lien",
            
            # Termes d'arnaque classiques
            "argent facile", "argent rapide", "revenus passifs", "gagner de l'argent",
            "devenir riche", "millionnaire", "fortune", "sans effort", "sans risque",
            "doublez votre argent", "triplez votre mise", "rendement", "investissement sûr",
            
            # Urgence et rareté
            "offre limitée", "dernière chance", "places limitées", "ne ratez pas",
            "opportunité unique", "aujourd'hui seulement", "avant fermeture"
        ]
        
        # Mots-clés suspects pour la détection
        self.suspicious_keywords = [
            # Termes liés à l'argent
            "monnaie", "cash", "liquide", "gratuit", "bonus", "prime", "commission", 
            "bénéfice", "profit", "gains", "revenus", "salaire", "rémunération", "financement",
            
            # Termes liés aux cryptomonnaies
            "crypto", "bitcoin", "ethereum", "btc", "eth", "wallet", "portefeuille", 
            "blockchain", "nft", "token", "mining", "minage", "altcoin", "defi",
            "staking", "trading", "exchange", "ico", "shitcoin", "pump", "dump",
            
            # Termes d'arnaque classiques
            "méthode", "technique", "secret", "privé", "exclusif", "garantie", "validé",
            "astuce", "truc", "combine", "système", "stratégie", "formule", "programme",
            "formation", "coaching", "mentorat", "masterclass", "webinaire",
            
            # Termes spécifiques aux arnaques
            "arnaque", "hack", "exploit", "faille", "bug", "glitch", "bypass",
            "contournement", "non détecté", "indétectable", "escroquerie", "fraude"
        ]
        
        # Schémas de messages suspects (expressions régulières)
        self.suspicious_patterns = [
            r"gagne[rz]?\s+\d+[€$]\s+(?:par|en)\s+\d+\s+(?:jour|heure|minute|seconde)",  # Gagnez 500€ par jour
            r"\d+[€$]\s+(?:par|en)\s+\d+\s+(?:jour|heure|minute|seconde)",  # 500€ par jour
            r"(?:nouvelle|secret|privé)\s+(?:méthode|technique)",  # Nouvelle méthode, technique secrète
            r"(?:argent|euros|dollars)\s+(?:facile|rapide|garanti)",  # Argent facile, euros garantis
            r"(?:paypal|boursorama|revolut|binance|coinbase)\s+\d{4}",  # PayPal 2024
            r"(?:contact|mp|dm|message)\s+(?:moi|privé)",  # Contact moi, MP moi
            r"(?:lien|link)\s+(?:en|dans)\s+(?:bio|profil|dm|mp)",  # Lien en bio, link dans DM
            r"parrain(?:age)?\s+(?:code|lien)",  # Parrainage code, lien parrainage
            r"code\s+(?:promo|parrain(?:age)?)",  # Code promo, code parrainage
            r"(?:utilise|utiliser|utilisez)\s+(?:mon|ce)\s+(?:code|lien)",  # Utilisez mon code
            r"(?:inscri(?:s|vez|ption))\s+(?:avec|via|par|grace|grâce)\s+(?:mon|ce|le)\s+(?:lien|code)",  # Inscrivez-vous avec mon lien
            r"(?:euros?|€|\$|dollars?)\s+(?:offert|gratuit|cadeau|bonus)",  # 10€ offerts, euros gratuits
            r"(?:jusqu'à|jusque?)\s+\d+[€$]",  # Jusqu'à 100€
            r"(?:recevez|recevr(?:ai|ez)|gagne[rz]?)\s+(?:jusqu'à|jusque?)?\s+\d+[€$]",  # Recevez jusqu'à 50€
        ]
        
        # Phrases de remplacement pour humilier les scammeurs
        self.humiliation_messages = [
            "Je suis un arnaqueur, venez me signaler en privé 😭",
            "Je passe mes journées à essayer d'arnaquer des gens parce que j'ai raté ma vie",
            "J'arnaque les gens parce que j'ai pas d'amis et j'ai besoin d'attention",
            "J'adore escroquer les gens et je suis fier de ne rien accomplir de ma vie",
            "Mes parents seraient tellement déçus s'ils savaient que je suis devenu un arnaqueur",
            "Je n'ai aucune compétence réelle, donc j'essaie d'arnaquer les gens sur Discord",
            "Signaler mon compte SVP, je suis un scammer et je mérite d'être banni",
            "Je suis tellement nul que je dois voler l'argent des autres pour me sentir important",
            "Regardez-moi, je suis un arnaqueur pathétique qui essaie de vous voler votre argent",
            "Mon QI est si bas que je pense que personne ne remarquera que je suis un scammer",
            "ALERTE ARNAQUE : Ne me faites pas confiance, je suis là pour vous escroquer !",
            "Je suis un scammer et je viens d'être attrapé par le système anti-arnaque 🤡",
            "Oups, je viens de me faire griller en essayant de vous arnaquer 😂",
            "Mon message d'arnaque vient d'être transformé en aveu public 🚨",
            "Je pensais être intelligent, mais le bot vient de me ridiculiser devant tout le monde",
        ]
        
        # Créer le dossier data s'il n'existe pas
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        
        # Charger la base de données
        self.load_db()
        
        print("🛡️ Module Anti-Scam initialisé!")
        print(f"🔍 Mots-clés à haut risque chargés: {len(self.high_risk_keywords)}")
        print(f"🔍 Mots-clés suspects chargés: {len(self.suspicious_keywords)}")
        print(f"🔍 Schémas suspects chargés: {len(self.suspicious_patterns)}")
        print(f"📊 Scammeurs enregistrés: {len(self.scammer_data)}")
    
    def load_db(self):
        """Charger la base de données des scammeurs"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r') as f:
                    data = json.load(f)
                    self.scammer_data = data
                print(f"✅ Base de données anti-scam chargée: {len(self.scammer_data)} utilisateurs")
            else:
                self.save_db()
                print("✅ Nouvelle base de données anti-scam créée")
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement de la base de données: {str(e)}")
            self.scammer_data = {}
    
    def save_db(self):
        """Sauvegarder la base de données des scammeurs"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.scammer_data, f, indent=4)
            return True
        except Exception as e:
            print(f"⚠️ Erreur lors de la sauvegarde de la base de données: {str(e)}")
            return False
    
    def is_suspicious_message(self, content):
        """Vérifier si un message est suspect (contient des mots-clés ou schémas d'arnaque)"""
        # Ignorer les messages trop courts
        if len(content) < 3:
            return False
            
        # Convertir en minuscules pour une recherche insensible à la casse
        content_lower = content.lower()
        
        # Vérifier les symboles monétaires directement (pour être sûr de les attraper)
        if "€" in content or "$" in content:
            print(f"🚨 Symbole monétaire détecté dans: {content[:30]}...")
            return True
        
        # Vérifier les mots exacts (pour éviter les faux positifs avec des sous-chaînes)
        words = re.findall(r'\b\w+\b', content_lower)
        for word in words:
            if word in ["euro", "euros", "paypal", "boursorama", "revolut", "sous", "argent", "fric"]:
                print(f"🚨 Mot financier exact détecté: {word}")
                return True
        
        # Vérifier les mots-clés à haut risque (un seul suffit)
        for keyword in self.high_risk_keywords:
            if keyword in content_lower:
                print(f"🚨 Mot-clé à haut risque détecté: {keyword}")
                return True
        
        # Compter les mots-clés suspects dans le message
        found_keywords = [keyword for keyword in self.suspicious_keywords if keyword in content_lower]
        keyword_count = len(found_keywords)
        
        # Vérifier les schémas suspects
        pattern_matches = [pattern for pattern in self.suspicious_patterns if re.search(pattern, content_lower)]
        
        # Journaliser les détections pour le débogage
        if keyword_count > 0 or pattern_matches:
            print(f"🔍 Analyse de message: {content_lower[:50]}...")
            if found_keywords:
                print(f"📝 Mots-clés trouvés ({keyword_count}): {', '.join(found_keywords)}")
            if pattern_matches:
                print(f"📝 Schémas suspects trouvés: {len(pattern_matches)}")
        
        # Un message est suspect s'il contient au moins 2 mots-clés suspects ou correspond à un schéma
        return keyword_count >= 2 or len(pattern_matches) > 0
    
    def get_humiliation_message(self):
        """Obtenir un message d'humiliation aléatoire"""
        return random.choice(self.humiliation_messages)
    
    def record_scam_attempt(self, user_id):
        """Enregistrer une tentative d'arnaque pour un utilisateur"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.scammer_data:
            self.scammer_data[user_id_str] = {
                "count": 1,
                "first_scam": datetime.now().isoformat(),
                "last_scam": datetime.now().isoformat(),
                "warnings": 0
            }
        else:
            self.scammer_data[user_id_str]["count"] += 1
            self.scammer_data[user_id_str]["last_scam"] = datetime.now().isoformat()
        
        self.save_db()
        return self.scammer_data[user_id_str]["count"]
    
    def should_increase_warning(self, user_id):
        """Déterminer si l'utilisateur doit recevoir un avertissement supplémentaire"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.scammer_data:
            return False
        
        # Augmenter l'avertissement tous les 3 messages d'arnaque
        if self.scammer_data[user_id_str]["count"] % 3 == 0:
            self.scammer_data[user_id_str]["warnings"] += 1
            self.save_db()
            return True
        
        return False
    
    def get_warning_level(self, user_id):
        """Obtenir le niveau d'avertissement d'un utilisateur"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.scammer_data:
            return 0
        
        return self.scammer_data[user_id_str]["warnings"]
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Intercepter les messages pour détecter les arnaques"""
        # Ignorer les messages des bots et les messages privés
        if message.author.bot or not message.guild:
            return
        
        # Ignorer les messages des administrateurs
        if message.author.guild_permissions.administrator:
            return
        
        # Ignorer les messages trop courts
        if len(message.content) < 3:
            return
            
        # Vérifier si le message est suspect
        is_suspicious = self.is_suspicious_message(message.content)
        
        # Journaliser pour le débogage
        if len(message.content) > 5:  # Ignorer les messages trop courts
            print(f"📨 Message de {message.author.name}: {message.content[:30]}... | Suspect: {is_suspicious}")
        
        if is_suspicious:
            # Enregistrer la tentative d'arnaque
            attempt_count = self.record_scam_attempt(message.author.id)
            
            # Obtenir le contenu original pour les logs
            original_content = message.content
            
            try:
                # Supprimer le message original
                await message.delete()
                print(f"🗑️ Message suspect de {message.author.name} supprimé: {original_content}")
            except Exception as e:
                print(f"⚠️ Erreur lors de la suppression du message suspect: {str(e)}")
                # Si la suppression échoue, on ne continue pas
                return
            
            try:
                # Créer un webhook pour imiter l'utilisateur
                webhooks = await message.channel.webhooks()
                webhook = None
                
                # Chercher un webhook existant ou en créer un nouveau
                for wh in webhooks:
                    if wh.name == "AntiScam System":
                        webhook = wh
                        break
                
                if webhook is None:
                    try:
                        webhook = await message.channel.create_webhook(name="AntiScam System")
                        print(f"🔧 Webhook 'AntiScam System' créé dans le canal {message.channel.name}")
                    except Exception as e:
                        print(f"⚠️ Erreur lors de la création du webhook: {str(e)}")
                        return
                
                # Obtenir un message d'humiliation
                humiliation = self.get_humiliation_message()
                
                # Envoyer le message modifié via le webhook
                await webhook.send(
                    content=humiliation,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none()
                )
                
                print(f"😈 Message suspect de {message.author.name} remplacé: {original_content} -> {humiliation}")
                
                # Vérifier si l'utilisateur doit recevoir un avertissement supplémentaire
                if self.should_increase_warning(message.author.id):
                    warning_level = self.get_warning_level(message.author.id)
                    await self.apply_sanctions(message.guild, message.author, warning_level)
                    print(f"⚠️ Niveau d'avertissement de {message.author.name} augmenté à {warning_level}")
            
            except Exception as e:
                print(f"⚠️ Erreur lors du remplacement du message suspect: {str(e)}")
            
            # Envoyer une alerte aux administrateurs
            await self.log_scam_attempt(message.author, message.channel, original_content, attempt_count)
    
    async def apply_sanctions(self, guild, member, warning_level):
        """Appliquer des sanctions en fonction du niveau d'avertissement"""
        try:
            # Niveau 1: Donner le rôle "Arnaqueur officiel"
            if warning_level == 1 and self.scammer_role_id:
                try:
                    scammer_role = guild.get_role(int(self.scammer_role_id))
                    if scammer_role:
                        await member.add_roles(scammer_role, reason="Tentatives d'arnaque répétées")
                        print(f"🏷️ Rôle 'Arnaqueur officiel' attribué à {member.name}")
                except Exception as e:
                    print(f"⚠️ Erreur lors de l'attribution du rôle: {str(e)}")
            
            # Niveau 2: Timeout pendant 1 heure
            elif warning_level == 2:
                try:
                    # Timeout pendant 1 heure (3600 secondes)
                    await member.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=3600), reason="Tentatives d'arnaque répétées")
                    print(f"⏳ Timeout de 1 heure appliqué à {member.name}")
                except Exception as e:
                    print(f"⚠️ Erreur lors de l'application du timeout: {str(e)}")
            
            # Niveau 3: Bannissement
            elif warning_level >= 3:
                try:
                    await guild.ban(member, reason="Tentatives d'arnaque répétées", delete_message_days=1)
                    print(f"🔨 Utilisateur {member.name} banni pour tentatives d'arnaque répétées")
                except Exception as e:
                    print(f"⚠️ Erreur lors du bannissement: {str(e)}")
        
        except Exception as e:
            print(f"⚠️ Erreur lors de l'application des sanctions: {str(e)}")
    
    async def log_scam_attempt(self, author, channel, content, attempt_count):
        """Envoyer une alerte aux administrateurs"""
        try:
            # Trouver le canal d'alerte
            alert_channel = None
            if self.alert_channel_id:
                alert_channel = self.bot.get_channel(int(self.alert_channel_id))
            
            if alert_channel:
                embed = discord.Embed(
                    title="🚨 Tentative d'Arnaque Détectée",
                    description=f"Une tentative d'arnaque a été détectée et neutralisée.",
                    color=discord.Color.red(),
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
                    name="Tentative n°",
                    value=f"{attempt_count}",
                    inline=True
                )
                
                embed.add_field(
                    name="Niveau d'avertissement",
                    value=f"{self.get_warning_level(author.id)}",
                    inline=True
                )
                
                embed.add_field(
                    name="Message original",
                    value=f"```{content[:1000]}```" if content else "*Aucun contenu textuel*",
                    inline=False
                )
                
                await alert_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi de l'alerte: {str(e)}")
    
    @commands.command(name="scammer_stats")
    @commands.has_permissions(administrator=True)
    async def scammer_stats(self, ctx, member: discord.Member = None):
        """Afficher les statistiques d'un scammer ou la liste des scammeurs
        
        Usage: !scammer_stats [@utilisateur]
        """
        if member:
            # Afficher les stats d'un utilisateur spécifique
            user_id = str(member.id)
            
            if user_id not in self.scammer_data:
                await ctx.send(f"✅ {member.mention} n'a pas de tentatives d'arnaque enregistrées.")
                return
            
            data = self.scammer_data[user_id]
            
            embed = discord.Embed(
                title="📊 Statistiques de Scammer",
                description=f"Statistiques pour {member.mention}",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="Tentatives d'arnaque",
                value=f"{data['count']}",
                inline=True
            )
            
            embed.add_field(
                name="Niveau d'avertissement",
                value=f"{data['warnings']}",
                inline=True
            )
            
            embed.add_field(
                name="Première tentative",
                value=f"<t:{int(datetime.fromisoformat(data['first_scam']).timestamp())}:R>",
                inline=False
            )
            
            embed.add_field(
                name="Dernière tentative",
                value=f"<t:{int(datetime.fromisoformat(data['last_scam']).timestamp())}:R>",
                inline=False
            )
            
            await ctx.send(embed=embed)
        
        else:
            # Afficher la liste des scammeurs
            if not self.scammer_data:
                await ctx.send("✅ Aucun scammer enregistré dans la base de données.")
                return
            
            embed = discord.Embed(
                title="📊 Liste des Scammers",
                description=f"Liste des utilisateurs ayant tenté des arnaques",
                color=discord.Color.red()
            )
            
            # Trier par nombre de tentatives
            sorted_scammers = sorted(
                self.scammer_data.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )
            
            for user_id, data in sorted_scammers[:10]:  # Limiter à 10 pour éviter les messages trop longs
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    user_name = f"{user.name} ({user.id})"
                except:
                    user_name = f"Utilisateur inconnu ({user_id})"
                
                embed.add_field(
                    name=user_name,
                    value=f"Tentatives: {data['count']} | Avertissements: {data['warnings']} | Dernière: <t:{int(datetime.fromisoformat(data['last_scam']).timestamp())}:R>",
                    inline=False
                )
            
            if len(sorted_scammers) > 10:
                embed.set_footer(text=f"Affichage des 10 premiers scammers sur {len(sorted_scammers)} au total.")
            
            await ctx.send(embed=embed)
    
    @commands.command(name="reset_scammer")
    @commands.has_permissions(administrator=True)
    async def reset_scammer(self, ctx, member: discord.Member):
        """Réinitialiser les statistiques d'un scammer
        
        Usage: !reset_scammer @utilisateur
        """
        user_id = str(member.id)
        
        if user_id not in self.scammer_data:
            await ctx.send(f"✅ {member.mention} n'a pas de tentatives d'arnaque enregistrées.")
            return
        
        # Supprimer les données de l'utilisateur
        del self.scammer_data[user_id]
        self.save_db()
        
        # Retirer le rôle "Arnaqueur officiel" si présent
        if self.scammer_role_id:
            try:
                scammer_role = ctx.guild.get_role(int(self.scammer_role_id))
                if scammer_role and scammer_role in member.roles:
                    await member.remove_roles(scammer_role, reason="Réinitialisation du statut de scammer")
            except Exception as e:
                print(f"⚠️ Erreur lors du retrait du rôle: {str(e)}")
        
        await ctx.send(f"✅ Les statistiques de scammer pour {member.mention} ont été réinitialisées.")
    
    @commands.command(name="set_scammer_role")
    @commands.has_permissions(administrator=True)
    async def set_scammer_role(self, ctx, role: discord.Role = None):
        """Définir le rôle à attribuer aux scammers
        
        Usage: !set_scammer_role @rôle
        """
        if role:
            # Mettre à jour le rôle dans les variables d'environnement
            os.environ['SCAMMER_ROLE_ID'] = str(role.id)
            self.scammer_role_id = str(role.id)
            
            await ctx.send(f"✅ Le rôle {role.mention} sera désormais attribué aux scammers.")
        else:
            # Afficher le rôle actuel
            if self.scammer_role_id:
                role = ctx.guild.get_role(int(self.scammer_role_id))
                if role:
                    await ctx.send(f"ℹ️ Le rôle actuel pour les scammers est: {role.mention}")
                else:
                    await ctx.send("⚠️ Le rôle configuré n'existe pas ou n'est pas accessible.")
            else:
                await ctx.send("ℹ️ Aucun rôle n'est configuré pour les scammers.")
    
    @commands.command(name="antiscam_help")
    async def antiscam_help(self, ctx):
        """Afficher l'aide du système anti-arnaque
        
        Usage: !antiscam_help
        """
        embed = discord.Embed(
            title="🛡️ Aide du Système Anti-Arnaque",
            description="Le système anti-arnaque détecte et neutralise automatiquement les tentatives d'escroquerie.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Fonctionnement",
            value="• Détection automatique des messages suspects\n"
                  "• Remplacement par des aveux humiliants\n"
                  "• Sanctions progressives contre les récidivistes\n"
                  "• Alertes aux administrateurs",
            inline=False
        )
        
        embed.add_field(
            name="Sanctions progressives",
            value="• Niveau 1: Attribution du rôle 'Arnaqueur officiel'\n"
                  "• Niveau 2: Timeout de 1 heure\n"
                  "• Niveau 3: Bannissement définitif",
            inline=False
        )
        
        embed.add_field(
            name="Commandes (Administrateurs)",
            value="• `!scammer_stats [@utilisateur]` : Statistiques d'un scammer ou liste des scammers\n"
                  "• `!reset_scammer @utilisateur` : Réinitialiser les statistiques d'un scammer\n"
                  "• `!set_scammer_role @rôle` : Définir le rôle à attribuer aux scammers\n"
                  "• `!test_scam_detection \"message\"` : Tester la détection d'arnaque sur un message",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="test_scam_detection")
    @commands.has_permissions(administrator=True)
    async def test_scam_detection(self, ctx, *, message: str):
        """Tester la détection d'arnaque sur un message
        
        Usage: !test_scam_detection "Votre message de test ici"
        """
        # Supprimer la commande originale
        try:
            await ctx.message.delete()
        except:
            pass
        
        # Vérifier si le message est suspect
        is_suspicious = self.is_suspicious_message(message)
        
        # Trouver les mots-clés à haut risque
        high_risk_found = [keyword for keyword in self.high_risk_keywords if keyword in message.lower()]
        
        # Trouver les mots-clés suspects
        suspicious_found = [keyword for keyword in self.suspicious_keywords if keyword in message.lower()]
        
        # Trouver les schémas suspects
        pattern_matches = [pattern for pattern in self.suspicious_patterns if re.search(pattern, message.lower())]
        
        # Créer un embed pour afficher les résultats
        embed = discord.Embed(
            title="🔍 Test de Détection d'Arnaque",
            description=f"**Message testé:**\n```{message}```",
            color=discord.Color.blue() if not is_suspicious else discord.Color.red()
        )
        
        embed.add_field(
            name="Résultat",
            value=f"**{'⚠️ SUSPECT' if is_suspicious else '✅ NON SUSPECT'}**",
            inline=False
        )
        
        if high_risk_found:
            embed.add_field(
                name="🚨 Mots-clés à haut risque détectés",
                value=", ".join(high_risk_found),
                inline=False
            )
        
        if suspicious_found:
            embed.add_field(
                name="🔍 Mots-clés suspects détectés",
                value=", ".join(suspicious_found[:15]) + (f" et {len(suspicious_found) - 15} autres..." if len(suspicious_found) > 15 else ""),
                inline=False
            )
            
            embed.add_field(
                name="📊 Nombre de mots-clés suspects",
                value=f"{len(suspicious_found)} (seuil: 2)",
                inline=True
            )
        
        if pattern_matches:
            embed.add_field(
                name="📝 Schémas suspects détectés",
                value=f"{len(pattern_matches)} schéma(s) suspect(s)",
                inline=True
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AntiScam(bot)) 