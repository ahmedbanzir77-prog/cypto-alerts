# Alertes crypto vers Telegram

Ce programme surveille les cinq adresses configurées et envoie une alerte Telegram à chaque nouvelle réception : montant, réseau, date et heure (Europe/Paris), adresse et identifiant de transaction.

Réseaux couverts : Bitcoin, Litecoin, Ethereum, USDT sur Ethereum (ERC-20) et Solana (SOL). Il fonctionne par vérification toutes les 30 secondes : une alerte peut donc arriver avec un léger décalage.

## Installation (Windows)

1. Installez [Python 3.10 ou plus récent](https://www.python.org/downloads/), en cochant « Add Python to PATH ».
2. Dans ce dossier, copiez `.env.example` en `.env`.
3. Ouvrez `.env` et collez **le nouveau token Telegram régénéré dans @BotFather**. Ne l'envoyez ni ici ni à personne.
4. Lancez `python monitor.py`.

Pour vérifier la configuration sans envoyer de crypto, lancez une fois `python monitor.py --test`. Le programme teste les cinq réseaux puis envoie un message « Test réussi » dans Telegram.

## Fonctionnement gratuit avec GitHub Actions

Le dossier contient déjà le workflow GitHub `.github/workflows/crypto-alerts.yml`. Il lance une vérification toutes les cinq minutes et conserve son état entre deux vérifications afin de ne pas envoyer deux fois la même alerte.

1. Créez un dépôt GitHub **public** et envoyez-y ce dossier, sans le fichier `.env`.
2. Dans GitHub : `Settings` → `Secrets and variables` → `Actions` → `New repository secret`.
3. Ajoutez `TELEGRAM_BOT_TOKEN` (la valeur est votre token Telegram) et `TELEGRAM_CHAT_ID` (votre identifiant Telegram).
4. Dans l'onglet `Actions`, autorisez les workflows puis lancez une fois « Alertes crypto Telegram » avec `Run workflow`.

Le token ne doit être ni écrit dans un fichier versionné, ni placé dans un message ou un commit. Un dépôt public révèle les adresses de réception et le code, mais pas les secrets GitHub.

Au premier lancement, le programme mémorise l'état actuel afin de ne pas vous envoyer les anciennes opérations. Il surveille ensuite les nouvelles transactions et affiche son activité dans la fenêtre.

## Le garder actif

Le programme doit rester ouvert pour alerter. Pour un usage continu, laissez la fenêtre ouverte sur un ordinateur allumé, ou créez une tâche Windows qui lance au démarrage :

```
python C:\chemin\vers\monitor.py
```

Pour une meilleure confidentialité et disponibilité, remplacez plus tard les endpoints publics dans `.env` par vos propres accès RPC Ethereum et Solana. Les adresses surveillées sont publiques : aucune clé privée ni phrase de récupération n'est requise.
