import os
import discord
from discord.ext import commands
import aiohttp
import re
import json
from datetime import datetime
import urllib.parse
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

class Sentinel(commands.Cog):
    """Cog for SentinelBot functionality - automatic link and file scanning"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Récupérer les clés API depuis config.py ou les variables d'environnement
        if config and hasattr(config, 'VIRUSTOTAL_API_KEY'):
            self.virustotal_api_key = config.VIRUSTOTAL_API_KEY
            print("🔑 Clé API VirusTotal chargée depuis config.py")
        else:
            self.virustotal_api_key = os.getenv('VIRUSTOTAL_API_KEY')
            print("🔑 Clé API VirusTotal chargée depuis les variables d'environnement")
            
        # Récupérer l'ID du canal de logs de sécurité
        if config and hasattr(config, 'SECURITY_LOG_CHANNEL_ID'):
            self.security_log_channel_id = config.SECURITY_LOG_CHANNEL_ID
            print("📢 Canal de logs de sécurité chargé depuis config.py")
        else:
            self.security_log_channel_id = os.getenv('SECURITY_LOG_CHANNEL_ID')
            print("📢 Canal de logs de sécurité chargé depuis les variables d'environnement")
            
        self.url_regex = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.pending_messages = {}  # Store messages that are being scanned
        
    @commands.Cog.listener()
    async def on_message(self, message):
        """Event listener for messages to scan links and files"""
        # Ignore messages from bots (including self)
        if message.author.bot:
            return
            
        # Check if VirusTotal API key is configured
        if not self.virustotal_api_key:
            return
            
        # Check if the message contains URLs or attachments
        urls = self.url_regex.findall(message.content)
        attachments = message.attachments
        
        if not urls and not attachments:
            return  # No URLs or attachments to scan
            
        # Ignorer les liens de remplacement (Rick Astley) pour éviter la double analyse
        if len(urls) == 1 and "dQw4w9WgXcQ" in urls[0]:  # ID de la vidéo Rick Astley
            return  # Ne pas analyser le lien de remplacement
            
        # Get the security log channel
        security_log_channel = None
        if self.security_log_channel_id:
            try:
                security_log_channel = self.bot.get_channel(int(self.security_log_channel_id))
            except (ValueError, TypeError):
                pass
                
        # Create a pending notification message
        pending_msg = await message.channel.send(
            f"⏳ {message.author.mention}, your message is being scanned for security threats. Please wait..."
        )
        
        # Store the message in pending_messages
        self.pending_messages[message.id] = {
            'message': message,
            'pending_msg': pending_msg,
            'urls': urls,
            'attachments': attachments,
            'scanned_items': 0,
            'total_items': len(urls) + len(attachments),
            'detections': 0
        }
        
        # Scan URLs
        for url in urls:
            # Ignorer les liens de remplacement (Rick Astley)
            if "dQw4w9WgXcQ" in url:  # ID de la vidéo Rick Astley
                continue  # Passer au lien suivant
            await self.scan_url(message.id, url, security_log_channel)
            
        # Scan attachments
        for attachment in attachments:
            await self.scan_attachment(message.id, attachment, security_log_channel)
    
    async def scan_url(self, message_id, url, security_log_channel=None):
        """Scan a URL using VirusTotal API"""
        if message_id not in self.pending_messages:
            return
            
        try:
            # Prepare the URL for scanning
            encoded_url = urllib.parse.quote_plus(url)
            
            # First, get the URL ID from VirusTotal
            async with aiohttp.ClientSession() as session:
                headers = {
                    'x-apikey': self.virustotal_api_key
                }
                
                # Get URL ID
                async with session.post(
                    f'https://www.virustotal.com/api/v3/urls',
                    headers=headers,
                    data={'url': url}
                ) as response:
                    if response.status != 200:
                        await self.update_scan_status(message_id, error=f"Error scanning URL: {response.status}")
                        return
                        
                    result = await response.json()
                    analysis_id = result.get('data', {}).get('id')
                    
                    if not analysis_id:
                        await self.update_scan_status(message_id, error=f"Error getting analysis ID for URL")
                        return
                
                # Wait for analysis to complete and get the report
                async with session.get(
                    f'https://www.virustotal.com/api/v3/analyses/{analysis_id}',
                    headers=headers
                ) as response:
                    if response.status != 200:
                        await self.update_scan_status(message_id, error=f"Error getting URL analysis: {response.status}")
                        return
                        
                    result = await response.json()
                    
                    # Get the analysis stats
                    stats = result.get('data', {}).get('attributes', {}).get('stats', {})
                    malicious = stats.get('malicious', 0)
                    suspicious = stats.get('suspicious', 0)
                    
                    # Total detections
                    total_detections = malicious + suspicious
                    
                    # Seuil de détection abaissé à 1 pour être plus strict
                    is_malicious = total_detections >= 1
                    
                    # Log the scan result
                    if security_log_channel:
                        embed = discord.Embed(
                            title="🔍 URL Scan Result",
                            color=discord.Color.green() if not is_malicious else discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        
                        embed.add_field(name="URL", value=url, inline=False)
                        embed.add_field(name="Detections", value=f"{total_detections} ({malicious} malicious, {suspicious} suspicious)", inline=True)
                        embed.add_field(name="Status", value="✅ Safe" if not is_malicious else "❌ Potentially Malicious", inline=True)
                        embed.add_field(name="VirusTotal Link", value=f"[View Report](https://www.virustotal.com/gui/url/{encoded_url})", inline=False)
                        
                        message = self.pending_messages[message_id]['message']
                        embed.set_footer(text=f"User: {message.author.name} ({message.author.id})")
                        
                        await security_log_channel.send(embed=embed)
                    
                    # Update the pending message
                    if is_malicious:
                        self.pending_messages[message_id]['detections'] += 1
                        
                        # Stocker les informations de détection pour l'affichage final
                        if 'detection_details' not in self.pending_messages[message_id]:
                            self.pending_messages[message_id]['detection_details'] = []
                            
                        self.pending_messages[message_id]['detection_details'].append({
                            'type': 'url',
                            'content': url,
                            'malicious': malicious,
                            'suspicious': suspicious,
                            'total': total_detections,
                            'report_url': f"https://www.virustotal.com/gui/url/{encoded_url}"
                        })
                    
                    # Update scan status
                    await self.update_scan_status(message_id)
                    
        except Exception as e:
            await self.update_scan_status(message_id, error=f"Error scanning URL: {str(e)}")
    
    async def scan_attachment(self, message_id, attachment, security_log_channel=None):
        """Scan a file attachment using VirusTotal API"""
        if message_id not in self.pending_messages:
            return
            
        try:
            # Download the attachment
            file_bytes = await attachment.read()
            
            # Scan the file with VirusTotal
            async with aiohttp.ClientSession() as session:
                headers = {
                    'x-apikey': self.virustotal_api_key
                }
                
                # Get upload URL
                async with session.get(
                    'https://www.virustotal.com/api/v3/files/upload_url',
                    headers=headers
                ) as response:
                    if response.status != 200:
                        await self.update_scan_status(message_id, error=f"Error getting upload URL: {response.status}")
                        return
                        
                    result = await response.json()
                    upload_url = result.get('data')
                    
                    if not upload_url:
                        await self.update_scan_status(message_id, error=f"Error getting upload URL")
                        return
                
                # Upload the file
                form_data = aiohttp.FormData()
                form_data.add_field('file', file_bytes, filename=attachment.filename)
                
                async with session.post(
                    upload_url,
                    headers=headers,
                    data=form_data
                ) as response:
                    if response.status != 200:
                        await self.update_scan_status(message_id, error=f"Error uploading file: {response.status}")
                        return
                        
                    result = await response.json()
                    analysis_id = result.get('data', {}).get('id')
                    
                    if not analysis_id:
                        await self.update_scan_status(message_id, error=f"Error getting analysis ID for file")
                        return
                
                # Wait for analysis to complete and get the report
                async with session.get(
                    f'https://www.virustotal.com/api/v3/analyses/{analysis_id}',
                    headers=headers
                ) as response:
                    if response.status != 200:
                        await self.update_scan_status(message_id, error=f"Error getting file analysis: {response.status}")
                        return
                        
                    result = await response.json()
                    
                    # Get the analysis stats
                    stats = result.get('data', {}).get('attributes', {}).get('stats', {})
                    malicious = stats.get('malicious', 0)
                    suspicious = stats.get('suspicious', 0)
                    
                    # Total detections
                    total_detections = malicious + suspicious
                    
                    # Seuil de détection abaissé à 1 pour être plus strict
                    is_malicious = total_detections >= 1
                    
                    # Get file hash for the report link
                    file_info = result.get('meta', {}).get('file_info', {})
                    sha256 = file_info.get('sha256', '')
                    
                    # Log the scan result
                    if security_log_channel:
                        embed = discord.Embed(
                            title="🔍 File Scan Result",
                            color=discord.Color.green() if not is_malicious else discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        
                        embed.add_field(name="File", value=attachment.filename, inline=False)
                        embed.add_field(name="Size", value=f"{attachment.size / 1024:.2f} KB", inline=True)
                        embed.add_field(name="Detections", value=f"{total_detections} ({malicious} malicious, {suspicious} suspicious)", inline=True)
                        embed.add_field(name="Status", value="✅ Safe" if not is_malicious else "❌ Potentially Malicious", inline=True)
                        
                        if sha256:
                            embed.add_field(name="VirusTotal Link", value=f"[View Report](https://www.virustotal.com/gui/file/{sha256})", inline=False)
                        
                        message = self.pending_messages[message_id]['message']
                        embed.set_footer(text=f"User: {message.author.name} ({message.author.id})")
                        
                        await security_log_channel.send(embed=embed)
                    
                    # Update the pending message
                    if is_malicious:
                        self.pending_messages[message_id]['detections'] += 1
                        
                        # Stocker les informations de détection pour l'affichage final
                        if 'detection_details' not in self.pending_messages[message_id]:
                            self.pending_messages[message_id]['detection_details'] = []
                            
                        self.pending_messages[message_id]['detection_details'].append({
                            'type': 'file',
                            'content': attachment.filename,
                            'malicious': malicious,
                            'suspicious': suspicious,
                            'total': total_detections,
                            'sha256': sha256
                        })
                    
                    # Update scan status
                    await self.update_scan_status(message_id)
                    
        except Exception as e:
            await self.update_scan_status(message_id, error=f"Error scanning file: {str(e)}")
    
    async def update_scan_status(self, message_id, error=None):
        """Update the scan status for a message"""
        if message_id not in self.pending_messages:
            return
            
        pending_data = self.pending_messages[message_id]
        pending_data['scanned_items'] += 1
        
        # Check if all items have been scanned
        if pending_data['scanned_items'] >= pending_data['total_items']:
            message = pending_data['message']
            pending_msg = pending_data['pending_msg']
            
            if error:
                # Error occurred during scanning
                await pending_msg.edit(content=f"⚠️ {message.author.mention}, an error occurred while scanning your message: {error}")
            elif pending_data['detections'] > 0:
                # Malicious content detected
                detection_details = pending_data.get('detection_details', [])
                
                # Créer un embed pour afficher les détails des détections
                embed = discord.Embed(
                    title="🚨 Contenu malveillant détecté",
                    description=f"Le message de {message.author.mention} contenait du contenu potentiellement dangereux.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                for i, detail in enumerate(detection_details):
                    if detail['type'] == 'url':
                        embed.add_field(
                            name=f"URL malveillante #{i+1}",
                            value=f"**URL:** {detail['content']}\n"
                                  f"**Détections:** {detail['total']} ({detail['malicious']} malveillantes, {detail['suspicious']} suspectes)\n"
                                  f"**Rapport:** [Voir sur VirusTotal]({detail.get('report_url', 'https://www.virustotal.com')})",
                            inline=False
                        )
                    elif detail['type'] == 'file':
                        embed.add_field(
                            name=f"Fichier malveillant #{i+1}",
                            value=f"**Fichier:** {detail['content']}\n"
                                  f"**Détections:** {detail['total']} ({detail['malicious']} malveillantes, {detail['suspicious']} suspectes)\n"
                                  f"**Rapport:** [Voir sur VirusTotal](https://www.virustotal.com/gui/file/{detail['sha256']})",
                            inline=False
                        )
                
                # Supprimer le message original avant d'envoyer la notification
                try:
                    await message.delete()
                except discord.errors.NotFound:
                    pass  # Message already deleted
                
                # Créer un embed pour le message de remplacement au lieu d'un lien direct
                # Cela évite que le bot ne détecte et n'analyse son propre lien
                replacement_embed = discord.Embed(
                    title="🛡️ Contenu remplacé",
                    description=f"{message.author.mention} a essayé de partager du contenu malveillant. J'ai remplacé ce contenu par quelque chose de plus sûr.",
                    color=discord.Color.orange()
                )
                replacement_embed.add_field(
                    name="Lien de remplacement",
                    value="[Cliquez ici pour un contenu sûr](https://www.youtube.com/watch?v=dQw4w9WgXcQ)",
                    inline=False
                )
                
                # Envoyer l'embed au lieu d'un message avec un lien direct
                await message.channel.send(embed=replacement_embed)
                
                # Mettre à jour le message de notification avec les détails
                await pending_msg.edit(content=f"🚨 {message.author.mention}, contenu malveillant détecté dans votre message. Il a été supprimé pour des raisons de sécurité.", embed=embed)
            else:
                # No malicious content detected
                await pending_msg.edit(content=f"✅ {message.author.mention}, your message has been scanned and is safe.")
                
                # Delete the pending message after a delay
                await pending_msg.delete(delay=5)
            
            # Remove the message from pending_messages
            del self.pending_messages[message_id]

async def setup(bot):
    await bot.add_cog(Sentinel(bot)) 