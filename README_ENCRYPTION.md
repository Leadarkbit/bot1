# Chiffrement des Messages Discord

Ce module permet de chiffrer automatiquement tous les messages envoyés sur un serveur Discord, garantissant que seuls les membres du serveur peuvent lire les messages.

## Fonctionnalités

- **Chiffrement AES-256** : Tous les messages sont chiffrés avec AES-256, un standard de chiffrement robuste.
- **Chiffrement transparent** : Les utilisateurs n'ont pas besoin de gérer des clés ou d'installer des logiciels supplémentaires.
- **Protection contre la surveillance** : Discord et les entités externes ne peuvent pas lire les messages chiffrés.
- **Déchiffrement automatique** : Les messages sont automatiquement déchiffrés pour les membres du serveur.
- **Commandes de chiffrement/déchiffrement manuel** : Possibilité de chiffrer ou déchiffrer manuellement des messages.

## Configuration

1. **Ajouter la clé de chiffrement** : Dans votre fichier `.env`, ajoutez une clé de chiffrement :
   ```
   ENCRYPTION_KEY=votre_clé_de_chiffrement_de_64_caractères_hexadécimaux
   ```
   Si vous ne spécifiez pas de clé, une clé temporaire sera générée au démarrage du bot, mais elle sera perdue à chaque redémarrage.

2. **Installer les dépendances** : Assurez-vous d'avoir installé les dépendances nécessaires :
   ```
   pip install -r requirements.txt
   ```

## Utilisation

### Activer le chiffrement pour un serveur

Pour activer le chiffrement automatique des messages sur un serveur, un administrateur doit utiliser la commande :
```
!toggle_encryption
```

Une fois activé, tous les messages envoyés sur le serveur seront automatiquement chiffrés.

### Déchiffrer les messages

Les messages chiffrés sont automatiquement déchiffrés et envoyés par message privé aux membres du serveur qui ont activé le déchiffrement automatique.

Pour activer le déchiffrement automatique, utilisez la commande :
```
!auto_decrypt
```

### Commandes manuelles

- **Chiffrer un message** :
  ```
  !encrypt [message]
  ```
  ou répondez à un message avec `!encrypt` pour le chiffrer.

- **Déchiffrer un message** :
  ```
  !decrypt [message_chiffré]
  ```
  ou répondez à un message chiffré avec `!decrypt` pour le déchiffrer.

## Sécurité

- La clé de chiffrement est stockée uniquement sur le serveur où le bot est hébergé.
- Les messages sont chiffrés avant d'être envoyés à Discord.
- Même si quelqu'un exporte les logs d'un canal, les messages resteront chiffrés.
- Le chiffrement AES-256 est considéré comme sécurisé selon les standards actuels.

## Limitations

- Les fichiers joints aux messages ne sont pas chiffrés.
- Les messages envoyés avant l'activation du chiffrement ne sont pas chiffrés rétroactivement.
- Les commandes du bot ne sont pas chiffrées pour permettre leur fonctionnement normal.
- Si la clé de chiffrement est perdue, tous les messages chiffrés seront irrécupérables.

## Avertissement

Ce système de chiffrement est conçu pour protéger vos conversations contre la surveillance passive, mais n'est pas une solution de sécurité complète. Pour des communications hautement sensibles, envisagez d'utiliser des plateformes spécialisées dans la messagerie sécurisée. 