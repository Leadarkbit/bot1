# ExploiterBot + SentinelBot

A Discord bot that combines security pentesting capabilities with real-time protection features.

## Features

### ExploiterBot Features
- **CVE Lookup**: Search for CVE details and related exploits
- **Exploit Search**: Find exploits for specific software versions
- **Latest Exploits**: Get the most recent exploits from Exploit-DB
- **Server Scanning**: Scan IP addresses using Shodan to discover vulnerabilities

### SentinelBot Features
- **Automatic Link/File Analysis**: Scans all links and files shared in the server
- **VirusTotal Integration**: Uses VirusTotal API to check for malicious content
- **Threat Protection**: Automatically removes dangerous content
- **Security Logging**: Logs all security events for admin review

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following variables:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   SHODAN_API_KEY=your_shodan_api_key
   VIRUSTOTAL_API_KEY=your_virustotal_api_key
   SECURITY_LOG_CHANNEL_ID=your_log_channel_id
   ```
4. Run the bot:
   ```
   python main.py
   ```

## Commands

- `!cve CVE-XXXX-XXXXX` - Look up information about a specific CVE
- `!exploit [software] [version]` - Search for exploits for a specific software version
- `!latest` - Get the 5 most recent exploits from Exploit-DB
- `!scan ip [IP address]` - Scan an IP address using Shodan

## Security Features

The bot automatically scans all links and files shared in the server:
- Content with fewer than 3 detections on VirusTotal is allowed
- Content with 3 or more detections is automatically removed
- All scan results are logged in the designated security log channel

## Requirements

- Python 3.8+
- Discord Bot Token
- Shodan API Key
- VirusTotal API Key 