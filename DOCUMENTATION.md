# 🤖 Bot Discord public tout-en-un + panel web — Documentation complète

> Un bot que **n'importe quel serveur** peut ajouter, et que chaque admin configure lui-même sur un **site web** (connexion avec Discord) : accueil, vérification, rôles, tickets, niveaux, modération, automod, anti-raid, anti-nuke et journal.

| | |
|---|---|
| **Version** | 14.2.0 |
| **Type** | Bot public multi-serveurs (chaque serveur a sa propre configuration) |
| **Panel** | Site web intégré : page de présentation + tableau de bord (connexion Discord OAuth2) |
| **Langage** | Python 3.11+ (testé avec 3.15) · discord.py 2.4+ (testé avec 2.7.1) · aiohttp |
| **Base de données** | SQLite asynchrone, migrations automatiques |
| **Hébergement** | Ton PC + Cloudflare Tunnel pour commencer, puis 24 h/24 sur Railway **ou** un VPS |
| **Commandes** | 104 commandes slash + 1 menu clic droit (bot entièrement traduisible en anglais) |
| **Tests** | 96 tests automatiques |

---

## 📑 Sommaire

1. [Résumé : comment ça marche](#1--résumé--comment-ça-marche)
2. [Ce que fait le bot](#2--ce-que-fait-le-bot)
3. [Structure du projet](#3--structure-du-projet)
4. [Mise en ligne 24 h/24 (pas à pas)](#4--mise-en-ligne-24-h24-pas-à-pas)
5. [Utiliser le panel web](#5--utiliser-le-panel-web)
6. [Toutes les commandes](#6--toutes-les-commandes)
   - [Version gratuite et Premium](#6-bis--version-gratuite-et-premium)
7. [Explication de chaque module](#7--explication-de-chaque-module)
8. [Le panel web en détail (et sa sécurité)](#8--le-panel-web-en-détail-et-sa-sécurité)
9. [Base de données](#9--base-de-données)
10. [Maintenance, sauvegardes, mises à jour](#10--maintenance-sauvegardes-mises-à-jour)
11. [Dépannage](#11--dépannage)
12. [Bonnes pratiques de sécurité](#12--bonnes-pratiques-de-sécurité)
13. [Ajouter tes propres fonctionnalités](#13--ajouter-tes-propres-fonctionnalités)
14. [Historique du projet et suite possible](#14--historique-du-projet-et-suite-possible)

---

## 1. 🎯 Résumé : comment ça marche

```
   Internet                         Ta machine allumée 24 h/24 (Railway ou VPS)
 ┌────────────────────┐            ┌────────────────────────────────────────────┐
 │ panel.tondomaine.fr│  Cloudflare│  main.py  (un seul programme)              │
 │  (ton domaine)     │───────────▶│   ├─ le BOT  ◀──── connexion ──── Discord  │
 └────────────────────┘   HTTPS    │   ├─ le SITE WEB (panel, port 8080)        │
          ▲                        │   └─ la BASE  data/bot.db                  │
          │                        │        (config de chaque serveur, XP,      │
   Les admins de chaque            │         tickets, sanctions, sessions…)     │
   serveur se connectent           └────────────────────────────────────────────┘
   avec leur compte Discord
```

1. Tu mets le bot en ligne **une seule fois** (section 4).
2. N'importe qui l'ajoute à son serveur avec le bouton « Ajouter à Discord » du site.
3. L'admin du serveur va sur le panel, clique sur **« Se connecter avec Discord »**, choisit son serveur, puis :
   - **✨ Tout créer automatiquement** : le bot crée les salons et rôles manquants ;
   - il ajuste les réglages (messages, règles, tickets, niveaux, sécurité…) ;
   - **📤 Publier les panneaux** : le bot poste les règles, le menu de notifications et le panneau de tickets.
4. C'est prêt. Chaque serveur a **sa propre configuration**, et personne ne peut toucher à celle d'un autre.

**Ton domaine Cloudflare** donne simplement l'adresse du panel (par exemple `https://panel.tondomaine.fr`) avec le HTTPS gratuit. Le bot, lui, tourne sur Railway ou sur ton VPS. Cloudflare seul ne peut pas faire tourner un bot Discord en permanence.

---

## 2. ✨ Ce que fait le bot

| Module | Ce qu'il fait |
|---|---|
| **Accueil** | Message de bienvenue avec avatar et compteur, message privé, rôle « Non vérifié » automatique, message de départ, logs. Message d'accueil avec le lien du panel quand le bot rejoint un serveur |
| **Vérification** | Panneau des règles avec un bouton « J'accepte » qui retire « Non vérifié » et donne « Membre » |
| **Notifications** | Menu déroulant pour choisir les rôles à mentionner (Annonces, Événements…) |
| **Tickets** | Types configurables, formulaire, salon privé, prise en charge, priorités, ajout ou retrait de membres, transcript HTML, avis de 1 à 5 ⭐, fermeture automatique des tickets inactifs, statistiques |
| **Niveaux** | XP par message, cooldown, bonus booster, rôles de récompense, `/rank`, classement paginé, gestion de l'XP |
| **Modération** | Avertissements avec sanctions automatiques, mute, kick, ban et ban temporaire, softban, unban, purge filtrée, lock, slowmode, notes, casier, statistiques |
| **Automod** | Invitations, spam, mentions en masse, mots interdits (détecte les contournements comme `1d.10t`) |
| **Sécurité** | Anti-raid (âge du compte, vague d'arrivées, lockdown) et anti-nuke (suppressions massives, bans en masse), whitelist, alerte en DM au propriétaire |
| **Logs** | Messages supprimés ou modifiés, pseudos, rôles, vocal, salons, rôles créés ou supprimés, bans |
| **Panel web** | Site de présentation, connexion Discord, liste de tes serveurs, configuration complète, création automatique, publication des panneaux, diagnostic, statistiques |

---

## 3. 📁 Structure du projet

```
discord-bot/
├── main.py                 # Démarre le bot ET le site web
├── .env.example            # Modèle des secrets (token, client secret, adresse du panel)
├── requirements.txt        # Dépendances
├── Dockerfile              # Image Docker (Railway et VPS)
├── docker-compose.yml      # VPS : bot + tunnel Cloudflare
├── railway.json            # Réglages Railway (healthcheck, redémarrage auto)
├── docker-entrypoint.sh    # Donne le volume /app/data au bot, puis le lance sans les droits root
├── RAILWAY.md              # Guide pas à pas pour passer le bot sur Railway
├── start.bat               # Lancer sur ton PC pour tester (Windows)
├── DOCUMENTATION.md        # Ce fichier
│
├── bot/                    # Cœur partagé
│   ├── defaults.json       # Valeurs par défaut de la config d'un serveur
│   ├── config.py           # Config PAR SERVEUR (cache + base) + validation des données du panel
│   ├── db.py               # Base SQLite async + migrations + sauvegarde
│   ├── panels.py           # Publication / mise à jour des panneaux
│   ├── diagnostic.py       # Vérification des salons, rôles et permissions
│   ├── embeds.py           # Style des messages (couleur du serveur)
│   ├── pagination.py       # Boutons ⏮️ ◀️ ▶️ ⏭️
│   └── utils.py            # Durées, logs, hiérarchie, lien du panel
│
├── cogs/                   # Un fichier = un module du bot
│   ├── welcome.py  verification.py  roles.py  tickets.py  levels.py
│   ├── moderation.py  automod.py  security.py  logs.py  admin.py
│
├── web/                    # Le panel
│   ├── server.py           # Serveur web, connexion Discord, API
│   └── static/             # index.html (site), dashboard.html + dashboard.js (panel), style.css
│
├── tests/                  # Tests automatiques (pytest)
└── data/                   # Créé automatiquement : bot.db, bot.log, backups/
```

---

## 4. 🚀 Mise en ligne 24 h/24 (pas à pas)

### Étape 1 : créer l'application Discord

1. Va sur <https://discord.com/developers/applications> et clique sur **New Application**. Donne-lui le nom de ton bot.
2. Onglet **Bot** :
   - clique sur **Reset Token** et copie le token (c'est `DISCORD_TOKEN`) ;
   - active **Server Members Intent** et **Message Content Intent** ;
   - laisse **Public Bot** activé, pour que tout le monde puisse l'ajouter.
3. Onglet **OAuth2** :
   - clique sur **Reset Secret** et copie le Client Secret (c'est `DISCORD_CLIENT_SECRET`) ;
   - dans **Redirects**, ajoute `https://panel.tondomaine.fr/callback` (avec ta vraie adresse) puis clique sur **Save**.

4. Onglet **General Information**, tout en bas :
   - **URL des Conditions d'Utilisation** : `https://panel.tondomaine.fr/terms`
   - **URL de la Politique de Confidentialité** : `https://panel.tondomaine.fr/privacy`
   - laisse **vides** « URL du point de terminaison des interactions » et « URL de vérification des rôles liés ». Le bot passe par la connexion Gateway : remplir le premier champ casserait les commandes slash.
   - Mets ton contact (e-mail ou invitation de ton serveur de support) dans la variable `CONTACT` : il s'affiche sur ces deux pages.

> ⚠️ Discord demande une **vérification** du bot (identité et justification des intents) quand il dépasse **100 serveurs**. Tu la fais depuis le portail quand ça arrive : le bot continue de marcher en attendant, mais il ne peut pas rejoindre plus de 100 serveurs.

### Étape 2 : mettre le code sur GitHub (privé)

Crée un dépôt **privé** sur GitHub et envoie-y le dossier `discord-bot`. Le fichier `.env` n'est **jamais** envoyé, `.gitignore` s'en charge.

### Étape 3 (option A, la plus simple) : Railway

Tout est expliqué pas à pas dans **[RAILWAY.md](RAILWAY.md)** : sauvegarde des données, GitHub privé, projet Railway, volume monté sur `/app/data`, variables, domaine Cloudflare, puis `/restore` pour remettre les données.

### Étape 3 (option B) : VPS + Docker + Cloudflare Tunnel

Le tunnel Cloudflare relie ton domaine au VPS sans ouvrir de port et fournit le HTTPS automatiquement.

1. Loue un petit VPS Linux (1 Go de RAM suffit) et installe Docker :
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
2. Dans **Cloudflare → Zero Trust → Networks → Tunnels** :
   - **Create a tunnel** (type Cloudflared), puis copie le **token** affiché (`CLOUDFLARE_TUNNEL_TOKEN`) ;
   - **Public Hostname** : sous-domaine `panel`, ton domaine, service **HTTP** → `bot:8080`.
3. Sur le VPS :
   ```bash
   git clone <ton dépôt privé> discord-bot && cd discord-bot
   cp .env.example .env
   nano .env            # remplis DISCORD_TOKEN, DISCORD_CLIENT_SECRET, PUBLIC_URL, CLOUDFLARE_TUNNEL_TOKEN
   docker compose up -d --build
   docker compose logs -f bot
   ```
4. Ouvre `https://panel.tondomaine.fr`.

Le bot et le tunnel redémarrent tout seuls en cas de plantage ou de redémarrage du VPS. La base est dans `./data` sur le VPS.

### Étape 4 : vérifier

- Dans les logs, tu dois voir « Module chargé » 10 fois, puis « Panel web en ligne : https://… » et « Connecté en tant que … ».
- `https://panel.tondomaine.fr/health` doit répondre `{"ok": true, "discord_ready": true, ...}`.
- Sur le site, clique sur **Ajouter à Discord**, ajoute le bot à ton serveur, puis **Ouvrir le panel**.

> 💡 Les commandes slash globales peuvent mettre jusqu'à 1 h à apparaître la première fois. Pour tester tout de suite sur ton serveur, mets son ID dans `DEV_GUILD_ID`, puis retire-le une fois en production.

### Étape 3 (option C, temporaire) : sur ton propre PC + Cloudflare Tunnel

Gratuit et parfait pour commencer. ⚠️ Le bot et le panel ne marchent **que pendant que ton PC est allumé**, connecté à Internet et que la fenêtre de `start.bat` est ouverte. Mets ton PC en mode « ne jamais se mettre en veille » (Paramètres → Système → Alimentation).

1. **Python** : installe Python 3.11 ou plus récent depuis python.org, en cochant « Add to PATH ».
2. **cloudflared** : dans un terminal, tape `winget install --id Cloudflare.cloudflared`.
3. **Tunnel** : dans **Cloudflare → Zero Trust → Networks → Tunnels** :
   - **Create a tunnel** → type **Cloudflared** → donne-lui un nom (ex. `bot-pc`) ;
   - à l'étape d'installation, copie seulement le **token** (la longue suite de caractères après `--token`). Inutile de lancer la commande proposée, `start.bat` s'en charge ;
   - **Public Hostname** : sous-domaine `panel`, ton domaine, type **HTTP**, URL **`localhost:8080`** → **Save**.
4. **Discord** : dans le portail, OAuth2 → Redirects, ajoute `https://panel.tondomaine.fr/callback`.
5. **Double-clique sur `start.bat`**. La première fois, il installe tout puis ouvre `.env` dans le Bloc-notes. Remplis :
   ```
   DISCORD_TOKEN=...
   DISCORD_CLIENT_SECRET=...
   PUBLIC_URL=https://panel.tondomaine.fr
   CLOUDFLARE_TUNNEL_TOKEN=...
   ```
   Enregistre, puis relance `start.bat`. Deux fenêtres s'ouvrent : le **bot** et le **tunnel**. Laisse-les ouvertes.
6. Ouvre `https://panel.tondomaine.fr` : c'est en ligne.

**Lancement automatique au démarrage du PC (facultatif)** : appuie sur Windows + R, tape `shell:startup` et valide, puis place dans ce dossier un **raccourci** vers `start.bat`.

**Passer à Railway plus tard** : rien à réécrire. Tu mets les mêmes variables dans Railway (option A), tu supprimes le « Public Hostname » du tunnel dans Cloudflare et tu le remplaces par le CNAME de Railway. Pour garder les données (config des serveurs, XP, tickets…), copie `data/bot.db` dans le volume Railway, ou repars de zéro.

---

## 5. 🖱️ Utiliser le panel web

### Pour les admins des serveurs (ce que tu peux leur expliquer)

1. Va sur `https://panel.tondomaine.fr/dashboard` et clique sur **Se connecter avec Discord**.
2. Tu vois tous les serveurs où tu as la permission « Gérer le serveur » :
   - **⚙️ Configurer** si le bot y est déjà ;
   - **➕ Ajouter le bot** sinon (le serveur est présélectionné).
3. Dans **Vue d'ensemble** :
   - **✨ Tout créer automatiquement** crée ce qui manque : les rôles Staff, Membre, Non vérifié, 4 rôles de notification et 4 rôles de niveau, les salons règles, rôles, support, bienvenue, au revoir, niveaux et les logs privés, et la catégorie Tickets. Rien n'est créé en double : si un élément existe déjà dans la config, il est gardé.
   - Le **diagnostic** liste ce qui ne va pas (salon manquant, rôle placé au-dessus du bot, permission manquante…).
4. Parcours les onglets et règle ce que tu veux :

| Onglet | Réglages |
|---|---|
| ⚙️ Général | Couleur des messages, pied de page, rôle Staff, salons de logs |
| 👋 Accueil | Activation, salon, message de bienvenue, message privé, message de départ |
| ✅ Vérification | Salon des règles, rôles Non vérifié et Membre, liste des règles |
| 🔔 Notifications | Salon du menu, choix proposés (nom → rôle) |
| 🎫 Tickets | Salon du panneau, catégorie, logs, types (emoji, nom, description), limite par membre, fermeture automatique |
| 📈 Niveaux | Activation, salon des annonces, message, rôles de récompense, XP min et max, cooldown, bonus booster, salons sans XP |
| 🔨 Modération | Sanctions automatiques (X warns → mute, kick ou ban) |
| 🤖 Automod | Invitations, mentions max, anti-spam, mots interdits, rôles ignorés |
| 🛡️ Sécurité | Anti-raid, anti-nuke, whitelists |

5. Clique sur **Enregistrer** dans la barre qui apparaît en bas. Les changements sont **immédiats**, sans redémarrage.
6. Retourne dans **Vue d'ensemble** et clique sur **📤 Publier les panneaux**. Republie-les après avoir modifié les règles, les notifications ou les types de tickets : le message existant est **mis à jour**, pas dupliqué.
7. ⚠️ Dans Discord, **Paramètres du serveur → Rôles**, glisse le rôle du bot **tout en haut**, sinon il ne peut pas donner les rôles.

> 💡 Astuce vérification : retire « Voir les salons » à `@everyone` sur tes salons et donne-la au rôle **Membre**. Les nouveaux ne verront que le salon des règles tant qu'ils n'ont pas cliqué sur « J'accepte ».

Variables utilisables dans les messages : `{mention}`, `{name}`, `{server}`, `{count}` (et `{level}` pour le message de niveau).

---

## 6. 🎮 Toutes les commandes

Les commandes de staff ne s'affichent que pour ceux qui ont la permission. Chaque serveur peut changer qui y a accès dans **Paramètres du serveur → Intégrations → le bot**.

### Pour tout le monde
| Commande | Effet |
|---|---|
| `/help` | Liste des commandes + lien du panel |
| `/dashboard` | Bouton vers le panel de ce serveur |
| `/invite` | Lien pour ajouter le bot ailleurs |
| `/rank [membre]` | Niveau, XP, progression, classement |
| `/leaderboard` | Top 100 paginé |
| `/ticket close [raison]` | Fermer son propre ticket |
| `/ping`, `/botinfo`, `/serverinfo`, `/userinfo` | Informations |

### Configuration (Gérer le serveur / Administrateur)
| Commande | Effet |
|---|---|
| `/check_config` | Diagnostic (le même que sur le panel) |
| `/setup_verify`, `/setup_notifications`, `/setup_ticket` | Publie le panneau dans le salon actuel (comme le bouton du panel) |
| `/welcome_test` | Aperçu du message de bienvenue |

### Tickets (staff)
`/ticket add <membre>` · `/ticket remove <membre>` · `/ticket priority <niveau>` · `/ticket stats` · boutons **🙋 Prendre en charge** et **🔒 Fermer**.

### Niveaux (Gérer le serveur)
`/xp add <membre> <montant>` · `/xp remove <membre> <montant>` · `/xp reset <membre>`

### Modération
| Commande | Permission | Effet |
|---|---|---|
| `/warn <membre> <raison>` | Modérer | Avertissement, DM au membre, escalade automatique |
| `/unwarn <cas>` | Modérer | Annule un avertissement |
| `/history <membre>` | Modérer | Casier paginé (sanctions et notes) |
| `/note <membre> <texte>` | Modérer | Note interne |
| `/mute <membre> <durée> [raison]` / `/unmute` | Modérer | Timeout (`10m`, `1h30m`, `7d` ; 28 jours maximum) |
| `/kick <membre> [raison]` | Expulser | Expulsion avec DM |
| `/ban <membre> [raison] [durée] [supprimer_messages]` | Bannir | Ban définitif, ou temporaire si une durée est donnée |
| `/softban`, `/unban <id>` | Bannir | Effacer les messages / débannir |
| `/purge <nombre> [membre] [bots] [contient]` | Gérer les messages | Suppression filtrée |
| `/slowmode`, `/lock`, `/unlock` | Gérer les salons | Gestion du salon |
| `/modstats` | Modérer | Actions par modérateur |

### Sécurité (Administrateur)
`/security` (état et derniers événements) · `/lockdown on|off [minutes]` · `/whitelist <utilisateur>`

### Réservées au propriétaire du bot (toi)
| Commande | Effet |
|---|---|
| `/backup` | Sauvegarde de toute la base, envoyée en fichier. Elle contient les données de **tous** les serveurs, d'où la restriction |
| `/restore fichier` | Remplace toute la base par une sauvegarde `.db` faite avec `/backup` (vérifiée avant), puis redémarre le bot. L'ancienne base est gardée dans `data/backups/`. Sert à déménager le bot, par exemple du PC vers Railway |
| `/sync` | Resynchronise les commandes slash |
| `/premium_admin give [serveur_id] [jours] [note]` | Offre Premium à un serveur (vide = à vie) |
| `/premium_admin remove [serveur_id]` | Retire le Premium offert |
| `/premium_admin list` | Liste des serveurs Premium (abonnés et offerts) |

Le propriétaire est le compte qui possède l'application sur le portail développeur.

### 💰 Économie, ⏰ rappels, 🎂 anniversaires
| Commande | Effet |
|---|---|
| `/balance [membre]` | Solde, classement et série de /daily |
| `/daily` | Récompense quotidienne, avec un bonus qui augmente si on revient chaque jour (série perdue après 48 h sans /daily) |
| `/work` | Gain aléatoire, avec un délai réglable |
| `/pay <membre> <montant>` | Donner de l'argent |
| `/richest` | Classement des plus riches |
| `/eco give` · `/eco take` · `/eco reset` | Gestion de l'économie (Gérer le serveur) |
| 💎 `/shop` · `/buy <objet>` · `/inventory` | Boutique configurée dans le panel (un objet peut donner un rôle) |
| `/rappel ajouter <dans> <texte>` · `/rappel liste` · `/rappel supprimer <n°>` | Rappels en message privé (3 actifs en gratuit, 25 en Premium) |
| `/anniversaire definir <jour> <mois>` · `/anniversaire retirer` · `/anniversaire prochains` | Anniversaires (annonce automatique le jour J, à l'heure du fuseau choisi) |

### 🎮 Mini-jeux (avec la monnaie du serveur)
| Commande | Effet |
|---|---|
| `/pileouface <mise> <pile|face>` | ×2 si tu gagnes |
| `/des <mise>` | Deux dés contre le bot ; le plus grand total gagne ×2 (égalité : mise rendue) |
| `/devine` | Devine un nombre de 1 à 100 en 7 essais ; le gain diminue à chaque essai |
| `/quiz` | Question de culture générale (FR ou EN selon la langue du serveur) ; le premier qui trouve gagne |
| 💎 `/roulette <mise> <pari>` | Rouge, noir, pair, impair (×2) ou un numéro de 0 à 36 (×36) |
| 💎 `/blackjack <mise>` | Blackjack contre le croupier, avec les boutons Tirer et Rester (blackjack naturel ×2,5) |

La mise maximum, les gains du quiz et de /devine se règlent dans l'onglet **Mini-jeux** du panel. La monnaie est virtuelle et n'a aucune valeur réelle.

### 🔊 Vocaux temporaires, 💡 suggestions et autres outils (v10)
| Commande / outil | Effet |
|---|---|
| Salon « ➕ Créer un salon » | Le rejoindre crée un vocal perso, supprimé automatiquement quand il est vide |
| `/vocal renommer` · `limite` · `verrouiller` · `deverrouiller` · `inviter` · `donner` | Gestion de son vocal temporaire par son propriétaire |
| `/suggestion <idée>` | Publie l'idée avec des votes 👍/👎 ; le staff clique sur ✅ ou ❌ et peut ajouter une réponse, et l'auteur est prévenu en DM |
| ⭐ Starboard | Un message qui atteint X réactions (emoji réglable) est recopié dans le salon starboard |
| Compteurs | Des vocaux renommés toutes les 10 min (« 👥 Membres : 1 234 ») : membres, humains, bots, en ligne, boosts, salons, rôles |
| Commandes perso | Déclencheur exact (`!ip`) ou mot contenu, réponse en texte ou encadrée, variables `{mention}` `{name}` `{server}` `{count}` |
| Menus de rôles | Panneaux de rôles à boutons ou en menu déroulant, avec emoji, aperçu et bouton **Publier** ; un ou plusieurs rôles au choix |
| Messages (panel) | Rédiger un embed avec aperçu et l'envoyer tout de suite ; 💎 ou le programmer (une fois, chaque jour, chaque semaine) |
| Sauvegarde (panel) | Télécharger la configuration en fichier `.json`, et l'importer sur ce serveur ou un autre |

Les limites gratuites sont appliquées par le bot. Au-delà, les éléments en trop sont signalés dans le panel et ne s'activent qu'en Premium.

### 🏅 Engagement, 🏦 banque et 👮 staff (v12)
| Commande / outil | Effet |
|---|---|
| `/profil [membre]` | Carte de profil : niveau, messages, fortune, séries, invitations, quêtes, parties gagnées, badges |
| `/succes [membre]` | Les 19 succès avec la progression de ceux qui restent ; chaque succès débloqué donne une récompense et est annoncé |
| `/quetes` | Les 3 quêtes du jour (les mêmes pour tout le serveur, tirées au sort) et 💎 la quête de la semaine, avec barres de progression |
| Série d'activité | Compte les jours d'affilée où le membre a parlé (record gardé), visible dans /profil |
| `/banque voir` · `deposer <montant\|tout>` · `retirer <montant\|tout>` | L'argent placé rapporte des intérêts une fois par jour (plafond réglable) |
| `/modstats [periode]` | Activité de chaque membre du staff sur 7, 30 ou 90 jours ou depuis le début : sanctions par type, tickets pris en charge, notes |
| `/unnote <numéro>` | Supprime une note interne |
| Panel → 👮 Accès au panel (💎) | Donne à un rôle l'accès à certaines parties du panel : Communauté, Modération, Tickets & modmail, Alertes & événements, Messages, Statistiques. La création auto, les modèles, la sauvegarde et cet onglet restent réservés aux admins, et le serveur web refuse toute modification hors des parties autorisées |
| Panel → Alertes (💎) | En plus de Twitch et YouTube : lives **Kick**, lives et nouvelles vidéos **TikTok** (sans API officielle : peut être en retard ou cesser de marcher si TikTok change son site), et n'importe quel **flux RSS / Atom** (les adresses internes sont refusées) |

### 📅 Événements, 🤖 IA et 🚩 modération avancée (v13)
| Commande / outil | Effet |
|---|---|
| `/evenement creer <titre> <date> <heure> [description] [places] [salon]` | Publie l'événement avec ✅ Participer / ❌ Me retirer ; les inscrits sont mentionnés X minutes avant (réglable) |
| `/evenement liste` · `/evenement annuler <numéro>` | Événements à venir, annulation |
| `/tournoi creer <nom> [places] [recompense] [salon]` | Tournoi avec bouton d'inscription |
| `/tournoi lancer` · `resultat <gagnant>` · `voir` · `annuler` | Tableau tiré au sort (exempts si besoin), le staff indique les gagnants, le champion reçoit la récompense |
| Parrainage (panel → Modmail & invitations) | L'inviteur reçoit de l'argent quand son invité est resté X jours |
| `/ia <question>` · salon d'aide IA · mention du bot (💎) | Réponse de l'IA à partir des règles et de la FAQ écrite dans le panel ; limite de questions par jour réglable |
| `/resume-ticket` (💎, staff) | Résumé du ticket (demande, ce qui a été fait, où on en est, prochaine étape), visible par toi seul |
| `/annonce-ia <sujet> [ton]` (💎) | Brouillon d'annonce avec aperçu et bouton **Publier ici** |
| Clic droit sur un message → Applications → **Signaler le message** | Le staff reçoit le signalement avec 🗑️ Supprimer / 🔇 Muter 10 min / ✅ Traité |
| `/signalements` | Signalements en attente |
| Ralenti automatique (panel → Automod) | Trop de messages en 10 s → mode lent quelques minutes, retiré tout seul |
| Journal des messages (panel → Modération + onglet dédié) | Messages modifiés et supprimés, filtres par salon, membre, type et mot ; désactivé par défaut, effacé après 7 jours (💎 30) |

**Assistant IA, côté propriétaire du bot :** crée une clé sur <https://platform.claude.com> (API Keys), mets-la dans `ANTHROPIC_API_KEY` du fichier `.env`, puis relance le bot. C'est toi qui paies l'usage (facturé par Anthropic). Modèle par défaut : Claude Opus 5.5 (4 $ / 20 $ par million de jetons en entrée / sortie), avec mise en cache de la FAQ et repli automatique sur un autre modèle si une demande est refusée. Une question coûte environ 1 à 2 centimes ; la limite par jour et par serveur (100 par défaut) plafonne la dépense. Pour un modèle moins cher, mets par exemple `ANTHROPIC_MODEL=claude-haiku-5-5`.

### 🌐 Site et 🖱️ panel (v14)
| Page / outil | Effet |
|---|---|
| `/` (accueil) | Toutes les fonctions regroupées par thème, « Prêt en 3 étapes », FAQ |
| `/commands` | Les commandes publiques avec recherche et filtre par module (FR / EN), générées automatiquement à partir du bot |
| `/premium` | Comparaison gratuit / Premium et bouton S'abonner (lien de la boutique Discord quand `PREMIUM_SKU_ID` est rempli) |
| `/status` | En ligne / hors ligne, latence, durée de fonctionnement, serveurs, membres, version (actualisé toutes les 30 s) |
| Aperçu de partage | Quand on colle le lien du site sur Discord ou un réseau social : image `/og.png` générée avec l'avatar et le nom du bot, titre et description. Nécessite `PUBLIC_URL` |
| Icône d'onglet | L'avatar du bot (`/favicon.png`) |
| Thème clair / sombre | Bouton ☀️ / 🌙 en haut de toutes les pages, choix mémorisé (sinon celui de l'appareil) |
| Panel : menu par catégories | Démarrage, Accueil, Communauté, Modération, Support & IA, Outils, Gestion ; chaque catégorie se replie |
| Panel : recherche | « 🔎 Rechercher un réglage » trouve n'importe quel réglage et y emmène directement |
| Panel : checklist | Vue d'ensemble → configuration en 8 étapes avec barre de progression et boutons « Régler → » |
| Panel : modifications | Point orange sur les onglets modifiés non enregistrés ; **Ctrl+S** pour enregistrer |
| Panel : 🧪 Tester dans Discord | Sous les aperçus (bienvenue, MP, au revoir, niveau, anniversaire) : envoie le vrai message dans le salon choisi, avec la configuration enregistrée |
| Panel : ↺ par défaut | À côté d'un réglage modifié : remet la valeur d'origine |
| Panel : 🆕 Nouveautés | Ce qui a changé à chaque version, badge « Nouveau » après une mise à jour |
| Panel : changement de serveur | Menu sous le nom du serveur, en haut à gauche |

### 👁️ Aperçu en direct
Dans le panel, sous chaque message personnalisable (bienvenue, message privé, au revoir, niveau, anniversaire) et sous les règles, notifications et types de tickets, un aperçu reproduit le rendu Discord : couleur, gras, mentions, boutons, menus. Il se met à jour à chaque frappe. En version gratuite, l'aperçu montre le texte par défaut, celui que le bot utilisera vraiment.

### 🌍 Langues
- **Panel et site** : bouton **🇬🇧 EN / 🇫🇷 FR** en haut à droite, choisi automatiquement selon la langue du navigateur.
- **Commandes** : les noms restent en français, mais les descriptions s'affichent en anglais pour les membres dont Discord est en anglais.
- **Langue du bot par serveur** (panel → Général) : les panneaux (règles, notifications, tickets), le bouton de vérification et les messages par défaut (bienvenue, au revoir, niveau, anniversaire) passent en anglais. Un message que l'admin a personnalisé est gardé tel quel.
- **Toutes les réponses du bot** (erreurs, modération, tickets, économie, jeux…) sont traduites automatiquement au moment de l'envoi, grâce à ot/translate.py et au dictionnaire ot/locale_en.py (environ 350 textes). Pour ajouter un texte, mets sa version française (avec {} pour les parties variables) et sa traduction dans ot/locale_en.py.
- **Pages légales** : /terms?lang=en et /privacy?lang=en, ouvertes automatiquement si le navigateur est en anglais.

### 💎 Premium
| Commande | Effet |
|---|---|
| `/premium` | Statut du serveur, avantages, bouton **S'abonner** et 🎁 **Essai gratuit** (7 jours, une fois par serveur, aussi dans l'onglet Premium du panel) |
| `/vote` | Lien de vote top.gg ; après avoir voté, le membre récupère sa récompense sur le serveur de son choix (réglable dans **Économie**, ×2 le week-end) |
| `/giveaway start <prix> <durée> [gagnants] [salon] [rôle_requis]` | Lance un giveaway avec bouton 🎉 Participer |
| `/giveaway end <id>` · `/giveaway reroll <id> [gagnants]` · `/giveaway list` | Terminer, refaire un tirage, voir les giveaways en cours |
| `/sondage creer <question> <choix A \| B \| C> [durée]` | Sondage à boutons (2 à 10 choix), résultats en direct |
| `/sondage fin <id>` | Termine un sondage |
| `/leaderboard periode:semaine` ou `mois` | Classements de la semaine ou du mois |

---

## 6 bis. 💎 Version gratuite et Premium

Chaque serveur est **gratuit** par défaut. Premium s'achète **par serveur**, avec un abonnement géré par Discord.

| | Gratuit | 💎 Premium |
|---|---|---|
| Accueil, vérification, rôles, tickets, niveaux, modération, automod, anti-raid, logs, panel | ✅ | ✅ |
| Couleur et pied de page des messages, messages de bienvenue, d'au revoir et de niveau personnalisés | Textes par défaut | ✅ |
| Transcripts HTML des tickets + avis ⭐ | ❌ | ✅ |
| Captcha de vérification | ❌ | ✅ |
| XP vocal, carte de rang en image, classements hebdo et mensuels | ❌ | ✅ |
| Giveaways et sondages | ❌ | ✅ |
| Alertes Twitch, YouTube, Kick, TikTok et flux RSS | ❌ | ✅ |
| 💰 Économie : /balance, /daily (série), /work, /pay, /richest | ✅ | ✅ |
| 💰 Boutique (/shop, /buy, /inventory), nom et emoji de la monnaie | ❌ | ✅ |
| ⏰ Rappels (/rappel) | 3 actifs par membre | 25 actifs |
| 🎂 Anniversaires : annonce le jour J | ✅ | ✅ |
| 🎂 Rôle anniversaire 24 h + message personnalisé | ❌ | ✅ |
| 📊 Statistiques en graphiques dans le panel | 7 jours | 7, 30 et 90 jours |
| 📜 Historique du panel (qui a modifié quoi) | ✅ | ✅ |
| 🎮 Mini-jeux : /pileouface, /des, /devine, /quiz | ✅ | ✅ |
| 🎮 Casino : /roulette, /blackjack | ❌ | ✅ |
| 👁️ Aperçu en direct des messages et panneaux dans le panel | ✅ | ✅ |
| 🔊 Vocaux temporaires (/vocal) | ✅ | ✅ |
| 💡 Suggestions avec votes + ⭐ starboard | ✅ | ✅ |
| 🖼️ Carte de bienvenue en image | ❌ | ✅ |
| 📊 Compteurs (salons qui affichent membres, en ligne, boosts…) | 2 | 5 |
| 💬 Commandes perso / réponses automatiques | 5 | 50 |
| 🎭 Menus de rôles perso (boutons ou menu) | 2 | 15 |
| 📨 Envoyer un message depuis le panel | ✅ | ✅ |
| ⏰ Messages programmés (une fois, chaque jour, chaque semaine) | ❌ | ✅ |
| 💾 Sauvegarde / import de la configuration | ✅ | ✅ |
| ⏳ Avertissements qui expirent (30 jours par défaut) | ✅ | ✅ |
| 🎣 Blocage des liens dangereux (phishing, faux Nitro/Steam) | ✅ | ✅ |
| 📝 Formulaire personnalisé par type de ticket (5 questions) | ❌ | ✅ |
| 📬 Modmail (tickets par message privé au bot) | ✅ | ✅ |
| 📨 Suivi des invitations (/invitations) | ✅ | ✅ |
| 🧩 Modèles de configuration + 🪄 assistant de démarrage | ✅ | ✅ |
| 🏅 Succès et badges (19), /profil | ✅ | ✅ |
| 📜 Quêtes du jour (3 par jour) + série d'activité | ✅ | ✅ |
| 🏆 Quête de la semaine | ❌ | ✅ |
| 🏦 Banque avec intérêts quotidiens | 1 % fixe | Taux réglable (0 à 10 %) |
| 👮 Activité du staff (/modstats par période, onglet Statistiques) + /unnote | ✅ | ✅ |
| 👮 Accès au panel par rôle (modérateurs sans « Gérer le serveur ») | ❌ | ✅ |
| 📅 Événements avec inscription et rappel (/evenement) | ✅ | ✅ |
| 🎁 Essai Premium gratuit (une fois par serveur) | ✅ 7 jours | — |
| 🗳️ Récompense de vote top.gg (/vote) | ✅ | ✅ |
| 🏆 Tournois à élimination directe (/tournoi) | 16 joueurs | 64 joueurs |
| 🤝 Récompense de parrainage (invité resté X jours) | ✅ | ✅ |
| 🤖 Assistant IA : FAQ (/ia, salon, mention), /resume-ticket, /annonce-ia | ❌ | ✅ |
| 🚩 Signalements par clic droit + /signalements | ✅ | ✅ |
| 🐢 Ralenti automatique des salons qui s'emballent | ✅ | ✅ |
| 🕵️ Journal des messages modifiés/supprimés dans le panel | 7 jours | jusqu'à 30 jours |
| 🌍 Panel, site et descriptions des commandes en anglais, langue du bot par serveur | ✅ | ✅ |
| Anti-nuke, lockdown automatique, alerte au propriétaire | ❌ (lockdown manuel ✅) | ✅ |

**Comment ça marche dans le code :** les réglages Premium sont listés dans `FREE_OVERRIDES` (`bot/config.py`). Sur un serveur gratuit, le bot utilise automatiquement les valeurs gratuites, même si l'admin a préparé autre chose dans le panel. Dès que le serveur passe Premium, ses réglages s'appliquent sans redémarrage. Les commandes Premium appellent `require()` (`bot/premium.py`), qui affiche le bouton d'abonnement aux serveurs gratuits.

### Mettre en place l'abonnement Discord
1. Le bot doit appartenir à une **équipe** (portail → Teams → crée une équipe, puis transfère l'application) et être **vérifié**.
2. Portail → ton application → **Monetization** : active la monétisation, renseigne tes informations de paiement (c'est toi qui le fais, Discord vérifie ton identité) et accepte les conditions.
3. **SKUs → Create SKU** : type **Guild Subscription**, choisis le nom (ex. « Premium ») et le prix mensuel, puis publie-le.
4. Copie l'**ID du SKU** dans la variable `PREMIUM_SKU_ID` et redémarre le bot.
5. C'est automatique ensuite : le bouton « S'abonner » apparaît dans `/premium`, dans les messages d'upsell et dans l'onglet Premium du panel. Le bot détecte les nouveaux abonnements, les renouvellements et les résiliations, et revérifie tout toutes les 6 heures.

**En attendant la vérification**, laisse `PREMIUM_SKU_ID` vide et offre Premium avec `/premium_admin give`, à des partenaires ou pour tester. Les serveurs gratuits voient alors « contacte le propriétaire du bot ».

### Alertes Twitch (facultatif)
YouTube, Kick, TikTok et RSS fonctionnent sans rien faire. Pour Twitch : sur <https://dev.twitch.tv/console>, clique sur **Register Your Application** (catégorie « Chat Bot », OAuth Redirect `http://localhost`), puis copie le Client ID et un Client Secret dans `TWITCH_CLIENT_ID` et `TWITCH_CLIENT_SECRET`.

---

## 7. 🧠 Explication de chaque module

### 🚪 Accueil (`cogs/welcome.py`)
À chaque arrivée, le module demande d'abord au module Sécurité si le membre est suspect. S'il l'est, le membre est expulsé et le message de bienvenue n'est pas envoyé. Sinon, le bot donne « Non vérifié », publie l'embed de bienvenue aux couleurs du serveur, envoie le DM et écrit le log. Au départ, il publie le message d'au revoir et note dans les logs la date d'arrivée et les rôles. Quand le bot **rejoint un nouveau serveur**, il poste un message avec le lien direct vers le panel de ce serveur.

### ✅ Vérification (`cogs/verification.py`)
Le bouton est **persistant** : il fonctionne encore après un redémarrage. Un clic donne « Membre », retire « Non vérifié », confirme en message privé et écrit un log.

### 🔔 Notifications (`cogs/roles.py`)
Les choix du menu viennent de la config du serveur. Un seul enregistrement de vue sert tous les serveurs : le bot retrouve les bons rôles au moment du clic.

### 🎫 Tickets (`cogs/tickets.py`)
1. L'utilisateur choisit un type, remplit le formulaire (sujet, détails), puis la limite de tickets ouverts est vérifiée.
2. Le salon `support-0001` est créé dans la catégorie. Seuls l'utilisateur, le staff et le bot le voient.
3. Le staff peut le prendre en charge, changer la priorité (🟢 🟡 🟠 🔴) et ajouter ou retirer des membres.
4. À la fermeture, un **transcript HTML** façon Discord part dans les logs et en DM à l'utilisateur, avec des boutons d'avis ⭐. Le salon est supprimé au bout de 5 s.
5. Toutes les 30 min, les tickets inactifs depuis le délai choisi pour leur serveur sont fermés.

### 📈 Niveaux (`cogs/levels.py`)
Le gain est un nombre aléatoire entre XP min et XP max, avec un bonus pour les boosters. Il n'y a pas de gain pendant le cooldown. Passer du niveau *n* au niveau *n + 1* coûte `5·n² + 50·n + 100` XP.

| Niveau | XP cumulée | Messages environ (20 XP) |
|---|---|---|
| 1 | 100 | 5 |
| 5 | 1 150 | 58 |
| 10 | 4 675 | 234 |
| 20 | 23 850 | 1 193 |
| 30 | 67 525 | 3 376 |

En passant un niveau, le membre reçoit tous les rôles des paliers atteints, même ceux qu'il aurait ratés.

### 🔨 Modération (`cogs/moderation.py`)
Chaque action crée un **cas numéroté** et un log, et le membre reçoit un DM. La hiérarchie est vérifiée : impossible de sanctionner le propriétaire, quelqu'un de plus haut placé, ou soi-même. Après un `/warn`, l'escalade réglée dans le panel s'applique. Les bans temporaires sont levés automatiquement, même après un redémarrage.

### 🤖 Automod (`cogs/automod.py`)
Le staff et les rôles ignorés passent. Pour les autres, le bot cherche des invitations, trop de mentions, des mots interdits ou du spam. Il supprime le message, prévient l'auteur (message effacé au bout de 8 s), enregistre l'infraction et écrit un log. Le spam ajoute un mute de 5 min. Avant la recherche de mots interdits, le texte est normalisé : accents retirés, `1→i`, `0→o`, `3→e`, `@→a`, séparateurs retirés, lettres répétées réduites.
> ⚠️ Les mots interdits sont cherchés **à l'intérieur** du message, une fois les espaces retirés. Évite les mots très courts qui se cachent dans des mots normaux.

### 🛡️ Sécurité (`cogs/security.py`)
- **Anti-raid** : le membre est refusé si le serveur est en lockdown, si une vague d'arrivées dépasse le seuil (ce qui déclenche aussi un lockdown automatique de 5 min), ou si son compte est trop récent. Il reçoit un DM, puis il est expulsé ou banni, et l'action est enregistrée.
- **Anti-nuke** : le bot lit le journal d'audit en temps réel. Si quelqu'un (ni le propriétaire, ni le bot, ni une personne de la whitelist) dépasse les seuils, il est banni ou perd ses rôles, et le propriétaire reçoit une alerte en DM. Les bans faits avec `/ban` sont au nom du bot, donc ils ne déclenchent pas l'anti-nuke.

### 📋 Logs (`cogs/logs.py`)
Messages supprimés (avec les pièces jointes) ou modifiés, suppressions en masse, pseudos, rôles, timeouts, vocal, salons et rôles créés ou supprimés, bans et débans.

---

## 8. 🌐 Le panel web en détail (et sa sécurité)

**Fonctionnement :** le site tourne **dans le même programme** que le bot (`web/server.py`). Il lit et modifie directement la config en mémoire, et les changements sont donc instantanés.

| Adresse | Rôle |
|---|---|
| `/` | Site de présentation (nom, avatar, nombre de serveurs et de membres, bouton d'ajout) |
| `/dashboard` | Panel (application en une seule page) |
| `/login` → Discord → `/callback` | Connexion OAuth2 (scopes `identify` et `guilds` seulement) |
| `/health` | Vérification de santé utilisée par Railway et Docker |
| `/api/...` | API JSON du panel |

**Sécurité intégrée :**
- **Qui peut configurer quoi** : à **chaque** requête, le bot vérifie en direct sur Discord que l'utilisateur est propriétaire du serveur ou a la permission **Gérer le serveur**. Retirer cette permission à quelqu'un lui coupe l'accès immédiatement.
- **Validation** : tout ce qui arrive du navigateur est filtré (`sanitize` dans `bot/config.py`). Les clés inconnues sont ignorées, les types forcés, les textes limités à 2 000 caractères, les listes à 100 éléments et les dictionnaires à 25 entrées. Impossible d'injecter des réglages imprévus.
- **Sessions** : un identifiant aléatoire stocké en base, dans un cookie `HttpOnly`, `Secure` en HTTPS et `SameSite=Lax`, valable 7 jours.
- **Anti-CSRF** : chaque modification exige un en-tête spécial et une origine identique au site. Le paramètre `state` protège la connexion OAuth.
- **Anti-XSS** : le panel n'injecte jamais de texte venant de Discord en HTML (tout passe par `textContent`).
- En-têtes `X-Frame-Options: DENY`, `nosniff` et `Referrer-Policy`.
- Le panel ne demande **aucune** permission sur le compte de l'utilisateur : il ne voit que son pseudo et la liste de ses serveurs.

---

## 9. 🗄️ Base de données

Fichier `data/bot.db` (ou `DATABASE_PATH`). Elle est créée et mise à jour automatiquement (9 migrations).

| Table | Contenu |
|---|---|
| `guild_config` | **Config de chaque serveur** (JSON validé). Seules les valeurs modifiées s'ajoutent aux valeurs par défaut de `bot/defaults.json` |
| `web_sessions` | Sessions de connexion au panel |
| `levels` | XP, niveau, messages |
| `cases` | Sanctions numérotées |
| `notes` | Notes du staff |
| `tickets` | Tickets (numéro, type, sujet, priorité, prise en charge, statut, dates) |
| `tempbans` | Bans temporaires en cours |
| `security_logs` | Événements automod, anti-raid et anti-nuke |
| `settings` | Données techniques par serveur (ex. message de chaque panneau publié) |
| `schema_version` | Version du schéma |

Pour faire évoluer la base, **ajoute** une migration à la fin de `MIGRATIONS` dans `bot/db.py`, sans jamais modifier une entrée existante.

---

## 10. 🔧 Maintenance, sauvegardes, mises à jour

- **Mettre à jour le bot** :
  - Railway : pousse sur GitHub et le redéploiement est automatique. La base est conservée grâce au volume.
  - VPS : `git pull && docker compose up -d --build`
- **Sauvegarde automatique** (v14.2) : chaque nuit vers 4 h UTC, le bot compresse la base (`auto_….db.gz`), garde les 14 dernières dans `data/backups/` et t'envoie la copie en message privé (ou dans `OWNER_ALERT_CHANNEL_ID`). Réglages : `BACKUP_AUTO`, `BACKUP_HOUR`, `BACKUP_KEEP`.
- **Alertes** (v14.2) : démarrage, plantage, erreurs, serveurs ajoutés/retirés, abonnements et essais t'arrivent en message privé (`OWNER_ALERTS=off` pour couper). Pour être prévenu si Railway tombe, surveille `/health?strict=1` avec UptimeRobot (voir RAILWAY.md).
- **Sauvegarder** : `/backup` (toi seul) crée une copie compressée (`.db.gz`) dans `data/backups/` et te l'envoie ; `/restore` accepte `.db` et `.db.gz`. Sur un VPS, tu peux aussi copier `data/bot.db` tous les jours avec cron :
  `0 4 * * * cp /chemin/discord-bot/data/bot.db /sauvegardes/bot_$(date +\%F).db`
- **Restaurer** : `/restore` avec le fichier `.db` (toi seul). Le bot vérifie le fichier, redémarre et l'applique. Sans Discord : arrête le bot, remplace `data/bot.db` par la sauvegarde, puis relance.
- **Logs** : `data/bot.log` (rotation sur 5 fichiers de 5 Mo), ou l'onglet **Logs** de Railway, ou `docker compose logs -f bot`.
- **Tests** :
  ```bash
  pip install -r requirements.txt -r requirements-dev.txt
  pytest -q        # 96 tests
  ruff check .
  ```

---

## 11. 🚨 Dépannage

| Problème | Cause probable | Solution |
|---|---|---|
| `DISCORD_TOKEN manquant` | Variable absente | Ajoute-la (`.env` ou Variables Railway) |
| `PrivilegedIntentsRequired` | Intents non activés | Portail → Bot → active Server Members et Message Content |
| Le site affiche « connexion Discord pas encore configurée » | `PUBLIC_URL` ou `DISCORD_CLIENT_SECRET` manquant | Ajoute les deux et redémarre |
| Discord dit « Invalid OAuth2 redirect_uri » | Adresse de callback non enregistrée | Portail → OAuth2 → Redirects : `PUBLIC_URL` + `/callback`, à l'identique |
| « La connexion a échoué » après Discord | Client secret faux ou changé | Recopie le secret |
| Le site ne s'ouvre pas | DNS, tunnel ou port | Railway : domaine avec le port 8080. VPS : tunnel « Healthy » et service `http://bot:8080` |
| Erreur Cloudflare 525/526 | Mode SSL incompatible | Cloudflare → SSL/TLS → mode **Full** |
| La base repart de zéro à chaque déploiement | Pas de volume | Railway : volume monté sur `/app/data`. VPS : ne supprime pas `./data` |
| `Permission denied` sur `/app/data` | Ancienne image Docker | Mets à jour le bot : `docker-entrypoint.sh` règle les droits du volume tout seul |
| Le serveur n'apparaît pas dans « Mes serveurs » | Pas la permission Gérer le serveur, ou liste ancienne | Bouton **🔄 Actualiser** |
| « Le bot n'est pas sur ce serveur » | Bot pas encore ajouté | Bouton **➕ Ajouter le bot** |
| Les rôles ne sont pas donnés | Rôle du bot trop bas | Monte-le tout en haut (le diagnostic le signale) |
| Les commandes `/` n'apparaissent pas | Synchronisation globale lente | Attends jusqu'à 1 h, ou utilise `DEV_GUILD_ID` pour tester |
| Le menu montre d'anciens choix | Panneau non republié | 📤 Publier les panneaux |
| L'anti-raid expulse des gens normaux | Seuils trop stricts | Ajuste-les dans l'onglet Sécurité, ou utilise la whitelist |
| L'anti-nuke ne réagit pas | Permission « Voir les logs du serveur » absente | Donne-la au bot |
| Le bot est bloqué à 100 serveurs | Vérification Discord requise | Portail → App Verification |

Regarde toujours les logs : chaque erreur y est écrite en entier.

---

## 12. 🔐 Bonnes pratiques de sécurité

- ❌ Ne partage **jamais** `DISCORD_TOKEN`, `DISCORD_CLIENT_SECRET` ou `CLOUDFLARE_TUNNEL_TOKEN`, et ne les mets jamais sur GitHub. S'ils fuient, régénère-les immédiatement sur leur portail.
- ✅ Garde ton dépôt GitHub **privé**.
- ✅ Active la double authentification (2FA) sur Discord, GitHub, Railway et Cloudflare.
- ✅ Fais une sauvegarde (`/backup`) avant chaque grosse mise à jour.
- ✅ Teste les nouveautés sur un serveur de test avec `DEV_GUILD_ID` avant de les déployer.
- ✅ Les données des serveurs t'ont été confiées : ne les partage pas et supprime-les si un propriétaire te le demande.

---

## 13. 🧩 Ajouter tes propres fonctionnalités

1. Crée `cogs/mon_module.py` :
   ```python
   import discord
   from discord import app_commands
   from discord.ext import commands
   from bot import embeds
   from bot.config import gconf

   class MonModule(commands.Cog):
       def __init__(self, bot):
           self.bot = bot

       @app_commands.command(name="bonjour", description="Dit bonjour")
       @app_commands.guild_only()
       async def bonjour(self, interaction: discord.Interaction):
           cfg = gconf(interaction.guild)          # config de CE serveur
           await interaction.response.send_message(embed=embeds.base("Bonjour ! 👋", guild=interaction.guild))

   async def setup(bot):
       await bot.add_cog(MonModule(bot))
   ```
2. Ajoute `"mon_module"` à `COGS` dans `main.py`.
3. **Nouveau réglage configurable** :
   - ajoute-le dans `bot/defaults.json` (par exemple `"mon_module": {"actif": true}`). Il est automatiquement accepté et validé selon son type ;
   - affiche-le dans le panel : ajoute une ligne dans `SECTIONS` de `web/static/dashboard.js`, par exemple `{ path: "mon_module.actif", type: "toggle", label: "Activer" }`. Les types disponibles sont `text`, `textarea`, `number`, `toggle`, `color`, `select`, `channel`, `category`, `role`, `channels`, `roles`, `lines` et `ids` ;
   - lis-le dans le code avec `gconf(guild).get("mon_module", "actif")`.
4. Pour une nouvelle table, ajoute une migration dans `bot/db.py`.
5. Pour un bouton persistant, utilise `timeout=None`, un `custom_id` fixe, et `self.bot.add_view(...)` dans `cog_load`.

---

## 14. 📜 Historique du projet et suite possible

| Version | Contenu |
|---|---|
| v1 à v4 | Conversation DeepSeek : idées, feuille de route de 200 améliorations, ébauches de code |
| v5 | Réécriture complète et testée, pour un seul serveur, avec un fichier `config.json` |
| v6 | **Bot public multi-serveurs + panel web en ligne** : config par serveur en base, connexion Discord, création automatique des salons et rôles, publication des panneaux, diagnostic, site de présentation, déploiement Railway / VPS + Cloudflare Tunnel |
| v7 | **Gratuit + Premium** : abonnements Discord et accès offerts, verrouillage automatique des réglages Premium, giveaways, sondages, captcha, XP vocal, carte de rang, classements hebdo et mensuels, alertes Twitch et YouTube, pages légales, cadenas 💎 et onglet Premium dans le panel |

| v8 | **Économie** (portefeuille, daily avec série, work, pay, classement, boutique Premium avec rôles), **rappels**, **anniversaires** (annonce, rôle du jour Premium), **statistiques en graphiques** (7 j gratuit, 30/90 j Premium), **historique du panel**, **FR / EN** (panel, site, descriptions des commandes, textes par défaut selon la langue du serveur) |

| v9 | **Mini-jeux** (pile ou face, dés, devine le nombre, quiz FR/EN ; roulette et blackjack Premium), **aperçu en direct** façon Discord dans le panel (bienvenue, message privé, au revoir, niveau, anniversaire, panneaux), **bot 100 % anglais** (traduction automatique de toutes les réponses), **pages légales en anglais** |

| v10 | **Vocaux temporaires**, **suggestions + starboard**, **carte de bienvenue en image** (Premium), **compteurs**, **commandes perso**, **menus de rôles perso** avec aperçu, **envoi de messages** depuis le panel et **messages programmés** (Premium), **sauvegarde / import** de la configuration |

| v11 | **Avertissements qui expirent**, **blocage des liens dangereux** (+20 000 arnaques connues et détection des imitations), **formulaires de ticket** personnalisés (Premium), **modmail**, **suivi des invitations**, **4 modèles de configuration** (Gaming, Communauté, Pro/École, Streamer) et **assistant de démarrage** en 4 étapes |

| v12 | **19 succès** avec badges et récompenses, **/profil**, **quêtes du jour** (+ 💎 quête de la semaine), **séries d'activité**, **banque** avec intérêts, **activité du staff** (/modstats par période + panel), **/unnote**, 💎 **accès au panel par rôle**, 💎 alertes **Kick**, **TikTok** et **RSS** |

| v13 | **Événements** avec inscription et rappel, **tournois** à élimination directe, **parrainage** récompensé, 💎 **assistant IA** (FAQ, résumé de ticket, rédaction d'annonces), **signalements** par clic droit, **ralenti automatique**, **journal des messages** dans le panel, politique de confidentialité mise à jour |

| v14 | Site refait (**accueil** à jour, pages **Commandes**, **Premium**, **Statut**, aperçu de partage et icône), panel plus pratique (**menu par catégories**, **recherche** de réglages, **checklist** de configuration, **Ctrl+S**, points des onglets modifiés, boutons **Tester dans Discord** et **↺ par défaut**, **thème clair / sombre**, **Nouveautés**, changement rapide de serveur) |

| v14.1 | **Prêt pour Railway** : guide [RAILWAY.md](RAILWAY.md), commande **/restore** pour déménager les données, droits du volume réglés automatiquement, police installée dans l'image Docker pour les images générées, commandes du propriétaire cachées sur la page Commandes |

| **v14.2 (actuelle)** | **Fiabilité et croissance** : sauvegarde automatique chaque nuit envoyée au propriétaire, alertes en message privé (erreurs, plantages, serveurs, abonnements), `/health?strict=1` pour la surveillance externe, site protégé (limite de requêtes par adresse, politique CSP, HSTS), **top.gg** (nombre de serveurs + `/vote` récompensé), 🎁 **essai Premium gratuit** de 7 jours avec rappels |

**Idées pour la suite :** alertes Instagram/X, ménage des données des serveurs quittés, préparation du sharding (2 500 serveurs), découpage de `dashboard.js` et `web/server.py`.

---

*Documentation de la version 14.2.0. Mets-la à jour quand tu ajoutes une fonctionnalité.*
