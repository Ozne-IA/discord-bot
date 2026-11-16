"use strict";
/* Traduction FR → EN du site et du panel.
   Le site est écrit en français ; en anglais, les textes affichés sont remplacés à la volée
   (dictionnaire exact + quelques modèles pour les textes avec des nombres).
   Langue : choix mémorisé, sinon langue du navigateur. */

const LANG = (() => {
  try { const saved = localStorage.getItem("lang"); if (saved === "fr" || saved === "en") return saved; } catch { /* stockage indisponible */ }
  return (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";
})();
document.documentElement.lang = LANG;

const EN = {
  // --- commun / site
  "Panel": "Dashboard", "Mes serveurs": "My servers", "Déconnexion": "Log out", "Panel de configuration": "Dashboard",
  "gère ton serveur pour toi": "runs your server for you",
  "Accueil des nouveaux, vérification, tickets, niveaux, modération, anti-raid… Le tout se configure en quelques clics depuis un panel web, sans une ligne de code.":
    "Welcome messages, verification, tickets, levels, moderation, anti-raid… Everything is set up in a few clicks from a web dashboard, no code needed.",
  "➕ Ajouter à Discord": "➕ Add to Discord", "⚙️ Ouvrir le panel": "⚙️ Open the dashboard",
  "serveurs": "servers", "membres": "members", "commandes": "commands",
  "Accueil": "Welcome", "Message de bienvenue avec avatar, message privé, rôle automatique et message de départ.":
    "Welcome message with avatar, DM, automatic role and goodbye message.",
  "Vérification": "Verification", "Panneau de règles avec un bouton : les nouveaux n'accèdent au serveur qu'après avoir accepté.":
    "Rules panel with a button: newcomers only get access after accepting.",
  "Tickets": "Tickets", "Plusieurs types, formulaire, prise en charge, priorités, transcript HTML et avis 1 à 5 ⭐.":
    "Several types, form, claiming, priorities, HTML transcript and 1–5 ⭐ feedback.",
  "Niveaux": "Levels", "XP par message, rôles de récompense, /rank et classement, bonus pour les boosters.":
    "XP per message, reward roles, /rank and leaderboard, booster bonus.",
  "Modération": "Moderation", "Warn avec sanctions automatiques, mute, ban temporaire, casier, notes et purge filtrée.":
    "Warns with automatic punishments, mute, temp ban, case history, notes and filtered purge.",
  "Automod": "Automod", "Bloque les invitations, le spam, les mentions en masse et les mots interdits, même déguisés.":
    "Blocks invites, spam, mass mentions and banned words, even disguised ones.",
  "Anti-raid et anti-nuke": "Anti-raid & anti-nuke", "Repousse les vagues de faux comptes et sanctionne quiconque supprime salons ou rôles en masse.":
    "Stops waves of fake accounts and punishes anyone mass-deleting channels or roles.",
  "Journal complet": "Full logs", "Messages supprimés ou modifiés, rôles, pseudos, vocal, salons : tout est tracé.":
    "Deleted or edited messages, roles, nicknames, voice, channels: everything is logged.",
  "Premium": "Premium", "Giveaways, sondages, captcha, XP vocal, carte de rang, alertes Twitch/YouTube, personnalisation complète et anti-nuke.":
    "Giveaways, polls, captcha, voice XP, rank card, Twitch/YouTube alerts, full customization and anti-nuke.",
  "Version": "Version", "Conditions d'utilisation": "Terms of Service", "Confidentialité": "Privacy",

  // --- connexion
  "Connecte-toi avec ton compte Discord pour configurer les serveurs que tu gères.": "Log in with your Discord account to configure the servers you manage.",
  "Se connecter avec Discord": "Log in with Discord",
  "Le panel ne voit que ton pseudo et la liste de tes serveurs. Il ne peut ni lire tes messages ni agir en ton nom.":
    "The dashboard only sees your username and your server list. It can't read your messages or act on your behalf.",
  "La connexion a échoué. Réessaie.": "Login failed. Please try again.",
  "La connexion Discord n'est pas encore configurée sur ce bot (PUBLIC_URL / DISCORD_CLIENT_SECRET).": "Discord login isn't configured on this bot yet (PUBLIC_URL / DISCORD_CLIENT_SECRET).",

  // --- liste des serveurs
  "🔄 Actualiser": "🔄 Refresh", "⚙️ Configurer": "⚙️ Configure", "➕ Ajouter le bot": "➕ Add the bot", "💎 Premium": "💎 Premium",
  "Seuls les serveurs où tu as la permission « Gérer le serveur » apparaissent.": "Only servers where you have the “Manage Server” permission are listed.",
  "Aucun serveur à gérer.": "No server to manage.",
  "Crée un serveur ou demande la permission « Gérer le serveur », puis clique sur Actualiser.": "Create a server or ask for the “Manage Server” permission, then click Refresh.",
  "← Mes serveurs": "← My servers",

  // --- barre d'enregistrement / messages
  "⚠️ Tu as des modifications non enregistrées.": "⚠️ You have unsaved changes.", "Annuler": "Cancel", "Enregistrer": "Save",
  "✅ Configuration enregistrée. Pense à republier les panneaux si tu as modifié règles, notifications ou tickets.":
    "✅ Settings saved. Remember to republish the panels if you changed rules, notifications or tickets.",
  "Enregistre ou annule tes modifications d'abord.": "Save or cancel your changes first.",
  "Enregistre tes modifications d'abord.": "Save your changes first.",
  "Rien à créer, tout existe déjà 👍": "Nothing to create, everything already exists 👍",
  "Quitter sans enregistrer tes modifications ?": "Leave without saving your changes?",
  "Créer automatiquement tous les rôles et salons manquants (règles, rôles, support, logs, catégorie Tickets, rôles Staff/Membre/Non vérifié, notifications, niveaux) ?":
    "Automatically create all missing roles and channels (rules, roles, support, logs, Tickets category, Staff/Member/Unverified roles, notifications, levels)?",
  "Création en cours…": "Creating…", "Publication…": "Publishing…", "25 maximum.": "25 maximum.",

  // --- champs génériques
  "— Aucun —": "— None —", "— Choisir un rôle —": "— Choose a role —", "— Salon de logs —": "— Log channel —", "— Même salon —": "— Same channel —",
  "— Salon d'annonce —": "— Announcement channel —", "— Aucun rôle —": "— No role —", "— Pas de rôle —": "— No role —",
  "➕ Ajouter…": "➕ Add…", "⚠️ Introuvable (supprimé ?)": "⚠️ Not found (deleted?)", "Retirer": "Remove", "Supprimer": "Delete",
  "Un ID d'utilisateur par ligne": "One user ID per line",
  "Tu peux le régler dès maintenant : il s'appliquera dès que le serveur sera Premium.": "You can set it up now: it will apply as soon as the server is Premium.",

  // --- vue d'ensemble
  "Vue d'ensemble": "Overview", "tickets ouverts": "open tickets", "sanctions": "punishments", "membres classés": "ranked members",
  "🚀 Installation rapide": "🚀 Quick setup",
  "1. Crée automatiquement ce qui manque → 2. Ajuste les réglages dans le menu → 3. Publie les panneaux.": "1. Auto-create what's missing → 2. Adjust settings in the menu → 3. Publish the panels.",
  "Il me manque les permissions « Gérer les rôles » et « Gérer les salons ».": "I'm missing the “Manage Roles” and “Manage Channels” permissions.",
  "✨ Tout créer automatiquement": "✨ Create everything automatically", "📤 Publier / mettre à jour les panneaux": "📤 Publish / update panels",
  "🩺 Diagnostic : tout est bon ✅": "🩺 Diagnostics: all good ✅", "💎 Serveur Premium : toutes les fonctionnalités sont actives.": "💎 Premium server: every feature is active.",
  "Version gratuite. ": "Free version. ", "Découvrir Premium →": "Discover Premium →",

  // --- sections
  "Statistiques": "Statistics", "Général": "General", "Notifications": "Notifications", "Économie": "Economy",
  "Anniversaires & rappels": "Birthdays & reminders", "Giveaways & sondages": "Giveaways & polls", "Alertes Twitch / YouTube": "Twitch / YouTube alerts",
  "Sécurité": "Security", "Historique": "History",
  "Apparence des messages et salons de logs.": "Message appearance and log channels.",
  "Langue du bot sur ce serveur": "Bot language on this server", "Textes par défaut des panneaux et messages automatiques.": "Default texts of panels and automatic messages.",
  "Couleur des messages": "Message color", "Pied de page": "Footer", "Ex : Mon Serveur • Bot officiel": "e.g. My Server • Official bot",
  "Rôle Staff": "Staff role", "Voit et gère les tickets, ignoré par l'automod.": "Sees and handles tickets, ignored by automod.",
  "Salon de logs": "Log channel", "Privé, réservé au staff. Reçoit tout le journal.": "Private, staff only. Receives all logs.",
  "Logs de modération": "Moderation logs", "Sanctions, automod, sécurité. Vide = salon de logs.": "Punishments, automod, security. Empty = log channel.",
  "Ce qui se passe quand quelqu'un rejoint ou quitte le serveur.": "What happens when someone joins or leaves the server.",
  "Activer les messages de bienvenue": "Enable welcome messages", "Salon de bienvenue": "Welcome channel", "Message de bienvenue": "Welcome message",
  "Variables : {mention} {name} {server} {count}": "Variables: {mention} {name} {server} {count}",
  "Envoyer aussi un message privé": "Also send a direct message", "Message privé": "Direct message", "Salon d'au revoir": "Goodbye channel",
  "Facultatif.": "Optional.", "Message d'au revoir": "Goodbye message",
  "Les nouveaux reçoivent « Non vérifié », puis « Membre » quand ils acceptent les règles.": "Newcomers get “Unverified”, then “Member” when they accept the rules.",
  "Salon des règles": "Rules channel", "Le panneau avec le bouton y sera publié.": "The panel with the button will be posted there.",
  "Rôle Non vérifié": "Unverified role", "Donné automatiquement à l'arrivée.": "Given automatically on join.", "Rôle Membre": "Member role",
  "Donné quand la personne clique sur « J'accepte ».": "Given when the person clicks “I accept”.", "Règles": "Rules", "Une règle par ligne.": "One rule per line.",
  "Respecte tout le monde.": "Respect everyone.", "Captcha anti-robot": "Anti-bot captcha",
  "Avant d'obtenir le rôle, il faut recopier un code affiché dans une image.": "Before getting the role, users must type a code shown in an image.",
  "Un menu où chacun choisit les sujets pour lesquels il veut être mentionné.": "A menu where everyone picks the topics they want to be pinged for.",
  "Salon du menu": "Menu channel", "Choix proposés": "Options", "Nom affiché dans le menu → rôle donné.": "Name shown in the menu → role given.",
  "Nom affiché": "Display name", "➕ Ajouter une notification": "➕ Add a notification",
  "Un panneau où les membres ouvrent un salon privé avec le staff.": "A panel where members open a private channel with staff.",
  "Salon du panneau": "Panel channel", "Catégorie des tickets": "Ticket category", "Les salons de tickets y sont créés.": "Ticket channels are created there.",
  "Logs des tickets": "Ticket logs", "Reçoit les transcripts. Vide = salon de logs.": "Receives transcripts. Empty = log channel.",
  "Types de tickets": "Ticket types", "Nom (ex : Support)": "Name (e.g. Support)", "Description courte": "Short description", "➕ Ajouter un type": "➕ Add a type",
  "Tickets ouverts max par membre": "Max open tickets per member", "Fermeture auto après (heures)": "Auto-close after (hours)",
  "Sans aucun message. 0 = jamais.": "With no message. 0 = never.", "Transcript HTML": "HTML transcript",
  "Copie de la conversation envoyée dans les logs et au membre à la fermeture.": "Copy of the conversation sent to logs and to the member when closed.",
  "Avis ⭐ après fermeture": "⭐ Feedback after closing", "Le membre note le support de 1 à 5.": "The member rates the support from 1 to 5.",
  "Les membres gagnent de l'XP en discutant.": "Members earn XP by chatting.", "Activer les niveaux": "Enable levels",
  "Salon des annonces": "Announcement channel", "Vide = dans le salon où la personne a parlé.": "Empty = in the channel where the person spoke.",
  "Message de passage de niveau": "Level-up message", "Variables : {mention} {name} {level}": "Variables: {mention} {name} {level}",
  "Rôles de récompense": "Reward roles", "Niveau atteint → rôle donné.": "Level reached → role given.", "➕ Ajouter un palier": "➕ Add a tier",
  "XP minimum par message": "Minimum XP per message", "XP maximum par message": "Maximum XP per message",
  "Délai entre deux gains (s)": "Cooldown between gains (s)", "Empêche de farmer en spammant.": "Prevents farming by spamming.",
  "Bonus des boosters": "Booster bonus", "1.5 = +50 % d'XP.": "1.5 = +50% XP.", "Salons sans XP": "Channels without XP", "Texte et vocal.": "Text and voice.",
  "Carte de rang en image": "Image rank card", "/rank affiche une belle carte aux couleurs du serveur.": "/rank shows a nice card in the server colors.",
  "XP en vocal": "Voice XP", "Gagné chaque minute en vocal (pas seul, pas muet, pas AFK).": "Earned every minute in voice (not alone, not muted, not AFK).",
  "XP vocal par minute": "Voice XP per minute",
  "Monnaie du serveur : /daily, /work, /pay, /balance, /richest. Boutique 💎 : /shop, /buy, /inventory.": "Server currency: /daily, /work, /pay, /balance, /richest. 💎 Shop: /shop, /buy, /inventory.",
  "Activer l'économie": "Enable economy", "Nom de la monnaie": "Currency name", "Emoji de la monnaie": "Currency emoji",
  "Gain de /daily": "/daily reward", "Bonus par jour de série": "Bonus per streak day", "Ajouté pour chaque jour consécutif (série max 30).": "Added for each consecutive day (max streak 30).",
  "Gain minimum de /work": "Minimum /work reward", "Gain maximum de /work": "Maximum /work reward", "Délai entre deux /work (minutes)": "/work cooldown (minutes)",
  "Boutique": "Shop", "Un objet peut donner un rôle quand on l'achète (place le rôle sous celui du bot).": "An item can give a role when bought (put the role below the bot's).",
  "Nom de l'objet (ex : VIP)": "Item name (e.g. VIP)", "Prix": "Price", "Description": "Description", "➕ Ajouter un objet": "➕ Add an item",
  "Les membres enregistrent leur date avec /anniversaire definir ; le bot la fête automatiquement. /rappel permet de programmer des rappels.":
    "Members save their date with /anniversaire definir; the bot celebrates it automatically. /rappel schedules reminders.",
  "Activer les anniversaires": "Enable birthdays", "Message d'anniversaire": "Birthday message", "Rôle « anniversaire » (24 h)": "Birthday role (24 h)",
  "Donné le jour J, retiré le lendemain.": "Given on the day, removed the next day.", "Fuseau horaire": "Time zone",
  "Activer /rappel": "Enable /rappel", "3 rappels actifs par membre en gratuit, 25 en Premium.": "3 active reminders per member on free, 25 on Premium.",
  "Lance des concours (/giveaway start) et des sondages à boutons (/sondage creer) directement dans Discord.": "Run giveaways (/giveaway start) and button polls (/sondage creer) right in Discord.",
  "Rôle gestionnaire des giveaways": "Giveaway manager role", "En plus des personnes qui ont « Gérer le serveur ».": "In addition to people with “Manage Server”.",
  "Annonce automatique des lives et des nouvelles vidéos (vérification toutes les 3 minutes). Variables : {name} {title} {url} {game}. Tu peux mettre @everyone ou mentionner un rôle dans le message.":
    "Automatic announcement of streams and new videos (checked every 3 minutes). Variables: {name} {title} {url} {game}. You can use @everyone or mention a role in the message.",
  "Chaînes YouTube": "YouTube channels", "Ex : @MrBeast ou https://youtube.com/@MrBeast": "e.g. @MrBeast or https://youtube.com/@MrBeast",
  "Chaînes Twitch": "Twitch channels", "Le pseudo tel qu'il apparaît dans twitch.tv/pseudo": "The username as shown in twitch.tv/username",
  "@pseudo, lien ou ID de chaîne (UC…)": "@handle, link or channel ID (UC…)", "Pseudo Twitch (ex : zerator)": "Twitch username (e.g. zerator)",
  "Message (vide = message par défaut)": "Message (empty = default message)",
  "➕ Ajouter une chaîne YouTube": "➕ Add a YouTube channel", "➕ Ajouter une chaîne Twitch": "➕ Add a Twitch channel",
  "Les alertes Twitch ne sont pas encore activées sur ce bot (le propriétaire doit ajouter les clés Twitch). YouTube fonctionne.":
    "Twitch alerts aren't enabled on this bot yet (the owner must add the Twitch keys). YouTube works.",
  "💎 Module Premium : tu peux le préparer, il s'activera avec Premium.": "💎 Premium module: you can prepare it, it will turn on with Premium.", "Voir Premium →": "See Premium →",
  "Sanctions automatiques selon le nombre d'avertissements actifs (/warn).": "Automatic punishments based on the number of active warnings (/warn).",
  "Sanctions automatiques": "Automatic punishments", "Minutes : durée du mute.": "Minutes: mute duration.", "warns →": "warns →",
  "🔇 Mute": "🔇 Mute", "👢 Expulsion": "👢 Kick", "🔨 Bannissement": "🔨 Ban", "➕ Ajouter une étape": "➕ Add a step",
  "Filtre automatique des messages. Le staff est toujours ignoré.": "Automatic message filter. Staff is always ignored.",
  "Activer l'automod": "Enable automod", "Bloquer les invitations Discord": "Block Discord invites", "Mentions max par message": "Max mentions per message",
  "0 = pas de limite.": "0 = no limit.", "Anti-spam : messages": "Anti-spam: messages", "Au-delà : suppression + mute 5 min. 0 = désactivé.": "Beyond: deletion + 5 min mute. 0 = off.",
  "Anti-spam : en secondes": "Anti-spam: within seconds", "Mots interdits": "Banned words",
  "Un par ligne. Les variantes (1d10t, i.d.i.o.t) sont aussi détectées.": "One per line. Variants (1d10t, i.d.i.o.t) are detected too.", "Rôles ignorés": "Ignored roles",
  "Protection contre les raids (faux comptes en masse) et les nukes (destruction du serveur).": "Protection against raids (mass fake accounts) and nukes (server destruction).",
  "Anti-raid": "Anti-raid", "Âge minimum du compte (jours)": "Minimum account age (days)", "Arrivées avant alerte raid": "Joins before raid alert",
  "… en combien de secondes": "… within how many seconds", "Action sur un compte suspect": "Action on a suspicious account",
  "👢 Expulser": "👢 Kick", "🔨 Bannir": "🔨 Ban", "Lockdown automatique en cas de raid": "Automatic lockdown during a raid",
  "Refuse toutes les arrivées pendant 5 minutes.": "Refuses all joins for 5 minutes.", "Whitelist anti-raid": "Anti-raid whitelist", "Anti-nuke": "Anti-nuke",
  "Fenêtre de surveillance (s)": "Monitoring window (s)", "Suppressions de salons tolérées": "Allowed channel deletions",
  "Suppressions de rôles tolérées": "Allowed role deletions", "Bans manuels tolérés": "Allowed manual bans", "Créations de salons tolérées": "Allowed channel creations",
  "Sanction": "Punishment", "🎭 Retirer tous ses rôles": "🎭 Remove all their roles", "Whitelist anti-nuke": "Anti-nuke whitelist",
  "Le propriétaire du serveur est toujours ignoré.": "The server owner is always ignored.",

  // --- v10 : vocaux, communauté, compteurs, commandes, menus, messages, sauvegarde
  "Carte de bienvenue en image": "Welcome image card", "Avatar, pseudo et numéro de membre aux couleurs du serveur.": "Avatar, username and member number in the server colors.",
  "Vocaux temporaires": "Temporary voice", "Activer les vocaux temporaires": "Enable temporary voice channels",
  "Rejoindre le salon « créer » donne à chacun son propre vocal, supprimé automatiquement quand il est vide. Le propriétaire le gère avec /vocal (renommer, limite, verrouiller, inviter, donner).":
    "Joining the “create” channel gives everyone their own voice channel, deleted automatically when empty. The owner manages it with /vocal (rename, limit, lock, invite, give).",
  "Salon « ➕ Créer un salon »": "“➕ Create a channel” channel", "Le vocal à rejoindre pour créer le sien.": "The voice channel to join to create your own.",
  "— Choisir un vocal —": "— Choose a voice channel —", "Catégorie des vocaux créés": "Category for created channels",
  "Vide = même catégorie que le salon « créer ».": "Empty = same category as the “create” channel.", "— Même catégorie —": "— Same category —",
  "Nom des salons": "Channel name", "{name} = pseudo du propriétaire.": "{name} = owner's username.", "Places par défaut": "Default user limit", "0 = illimité.": "0 = unlimited.",
  "Suggestions & starboard": "Suggestions & starboard",
  "/suggestion publie une idée avec des votes 👍/👎 ; le staff l'accepte ou la refuse. Le starboard met en avant les messages qui reçoivent assez d'étoiles.":
    "/suggestion posts an idea with 👍/👎 votes; staff accepts or refuses it. The starboard highlights messages that get enough stars.",
  "Activer les suggestions": "Enable suggestions", "Salon des suggestions": "Suggestions channel", "Activer le starboard": "Enable starboard",
  "Salon du starboard": "Starboard channel", "Emoji": "Emoji", "Réaction qui compte (ex : ⭐ ou 🔥).": "Reaction that counts (e.g. ⭐ or 🔥).", "Réactions nécessaires": "Reactions needed",
  "Compteurs": "Counters",
  "Des salons vocaux dont le nom affiche un nombre (membres, en ligne, boosts…), mis à jour toutes les 10 minutes. Astuce : crée des vocaux que personne ne peut rejoindre.":
    "Voice channels whose name shows a number (members, online, boosts…), updated every 10 minutes. Tip: create voice channels nobody can join.",
  "2 en version gratuite, 5 en 💎 Premium.": "2 on the free version, 5 on 💎 Premium.", "➕ Ajouter un compteur": "➕ Add a counter",
  "👥 Membres": "👥 Members", "🙂 Humains": "🙂 Humans", "🤖 Bots": "🤖 Bots", "🟢 En ligne": "🟢 Online", "💎 Boosts": "💎 Boosts", "# Salons": "# Channels", "🎭 Rôles": "🎭 Roles",
  "— Salon vocal —": "— Voice channel —", "Texte, {} = le nombre (ex : 👥 Membres : {})": "Text, {} = the number (e.g. 👥 Members: {})",
  "Commandes perso": "Custom commands", "Commandes": "Commands",
  "Le bot répond automatiquement quand un message correspond au déclencheur (ex : « !regles », « !ip »).": "The bot replies automatically when a message matches the trigger (e.g. “!rules”, “!ip”).",
  "5 en version gratuite, 50 en 💎 Premium. Anti-spam : 5 s entre deux réponses.": "5 on the free version, 50 on 💎 Premium. Anti-spam: 5 s between replies.",
  "Déclencheur (ex : !regles)": "Trigger (e.g. !rules)", "Message exact": "Exact message", "Contient le mot": "Contains the word",
  "Réponse du bot ({mention} {name} {server} {count})": "Bot reply ({mention} {name} {server} {count})", "Encadré": "Embed", "➕ Ajouter une commande": "➕ Add a command",
  "Menus de rôles": "Role menus", "Menus": "Menus",
  "Crée tes propres panneaux de rôles (couleurs, jeux, régions…) à boutons ou en menu déroulant, puis publie-les.": "Create your own role panels (colors, games, regions…) with buttons or a dropdown, then publish them.",
  "2 en version gratuite, 15 en 💎 Premium. Enregistre avant de publier.": "2 on the free version, 15 on 💎 Premium. Save before publishing.",
  "Titre du menu (ex : 🎮 Tes jeux)": "Menu title (e.g. 🎮 Your games)", "— Salon —": "— Channel —", "Boutons": "Buttons", "Menu déroulant": "Dropdown",
  "Description (facultatif)": "Description (optional)", "Plusieurs rôles possibles": "Allow several roles", "Emoji ": "Emoji", "Texte (facultatif)": "Text (optional)",
  "➕ Ajouter un rôle": "➕ Add a role", "📤 Publier / mettre à jour": "📤 Publish / update", "Choisis tes rôles…": "Choose your roles…",
  "Messages": "Messages", "Envoyer un message": "Send a message", "Messages programmés": "Scheduled messages",
  "Rédige un message encadré aux couleurs du serveur et envoie-le tout de suite dans un salon.": "Write an embed in the server colors and send it right away to a channel.",
  "Sans mention": "No mention", "Titre": "Title", "Message (gras **texte**, italique *texte*, mentions <@&ID>…)": "Message (bold **text**, italic *text*, mentions <@&ID>…)",
  "📨 Envoyer maintenant": "📨 Send now", "Une fois": "Once", "Chaque jour": "Every day", "Chaque semaine": "Every week", "Message": "Message",
  "➕ Programmer un message": "➕ Schedule a message",
  "Envoyés automatiquement à la date choisie (fuseau horaire de l'onglet Anniversaires), une fois, chaque jour ou chaque semaine. Pense à enregistrer.":
    "Sent automatically at the chosen date (time zone from the Birthdays tab), once, daily or weekly. Remember to save.",
  "💎 Les messages programmés sont réservés aux serveurs Premium : tu peux les préparer dès maintenant.": "💎 Scheduled messages are for Premium servers: you can prepare them now.",
  "Sauvegarde": "Backup", "Sauvegarde de la configuration": "Configuration backup",
  "Télécharge toute la configuration de ce serveur dans un fichier, pour la restaurer plus tard ou la copier sur un autre serveur.":
    "Download this server's whole configuration as a file, to restore it later or copy it to another server.",
  "⬇️ Télécharger la sauvegarde": "⬇️ Download backup", "⬆️ Importer une sauvegarde": "⬆️ Import a backup",
  "L'import remplace la configuration actuelle et apparaît dans l'historique. Les XP, sanctions, tickets et l'économie ne sont pas concernés.":
    "Importing replaces the current configuration and shows up in the history. XP, punishments, tickets and the economy aren't affected.",
  "Ce fichier n'est pas une sauvegarde valide.": "This file isn't a valid backup.",
  "Remplacer toute la configuration de ce serveur par celle du fichier ?": "Replace this server's whole configuration with the file's?",
  "a envoyé un message": "sent a message", "a publié un menu de rôles": "published a role menu", "a importé une sauvegarde": "imported a backup",

  // --- v14 : site (accueil, Premium, commandes, statut) et panel
  "Fonctions": "Features", "Commandes": "Commands", "Statut": "Status", "Page d'accueil": "Home",
  "Accueil, tickets, niveaux, économie, mini-jeux, modération, anti-raid, alertes de live et assistant IA. Tout se règle en quelques clics depuis un panel web, sans une ligne de code.":
    "Welcome, tickets, levels, economy, mini-games, moderation, anti-raid, live alerts and an AI assistant. Everything is set up in a few clicks from a web dashboard, no code needed.",
  "Tout ce qu'il faut, dans un seul bot": "Everything you need, in one bot",
  "Active seulement ce dont tu as besoin : chaque module se règle séparément dans le panel.": "Turn on only what you need: each module is set up separately in the dashboard.",
  "👋 Accueil des nouveaux": "👋 Welcoming newcomers", "🛡️ Modération et sécurité": "🛡️ Moderation and security", "🎫 Support": "🎫 Support",
  "🎉 Communauté": "🎉 Community", "📺 Créateurs et outils": "📺 Creators and tools", "🤖 Panel web et IA": "🤖 Web dashboard and AI",
  "Bienvenue": "Welcome", "avec carte en image, message privé et au revoir": "with an image card, DM and goodbye",
  "par bouton, avec captcha anti-robot 💎": "by button, with anti-bot captcha 💎", "Rôles": "Roles",
  "de notifications et menus de rôles à boutons": "for notifications and button role menus", "Invitations": "Invites",
  "suivies, classement et parrainage récompensé": "tracked, leaderboard and rewarded referrals", "Avertissements": "Warnings",
  "qui expirent, sanctions automatiques, casier": "that expire, automatic punishments, record",
  ": spam, mots interdits, liens d'arnaque (+20 000 connus)": ": spam, banned words, scam links (20,000+ known)",
  ", ralenti automatique des salons": ", automatic channel slow mode", "par clic droit et journal des messages": "by right-click and message log",
  "par type, avec formulaire 💎, priorités et transcript": "by type, with form 💎, priorities and transcript",
  ": les membres écrivent au bot en privé": ": members DM the bot", "Avis": "Feedback", "⭐ après chaque ticket et statistiques": "⭐ after each ticket and statistics",
  "Résumé IA": "AI summary", "d'un ticket pour le staff 💎": "of a ticket for the staff 💎", ", carte de rang, rôles de récompense": ", rank card, reward roles",
  "Succès, quêtes": "Achievements, quests", "du jour et séries d'activité": "daily quests and activity streaks",
  "avec banque, boutique 💎 et": "with bank, shop 💎 and", "mini-jeux": "mini-games", "Événements, tournois": "Events, tournaments",
  ", giveaways, sondages, anniversaires": ", giveaways, polls, birthdays", "Twitch, YouTube, Kick, TikTok et RSS 💎": "Twitch, YouTube, Kick, TikTok and RSS 💎",
  "💎 et envoi depuis le panel": "💎 and sending from the dashboard", ", commandes perso, vocaux temporaires": ", custom commands, temporary voice channels",
  "avec votes et starboard": "with votes and starboard", "Assistant de démarrage": "Setup wizard", "et modèles prêts à l'emploi": "and ready-made templates",
  "des messages, boutons Tester": "of messages, Test buttons", ", historique, accès par rôle 💎": ", history, role-based access 💎",
  "qui répond avec ta FAQ 💎, en français et en anglais": "that answers with your FAQ 💎, in French and English",
  "Prêt en 3 étapes": "Ready in 3 steps", "Ajoute le bot": "Add the bot", "Clique sur « Ajouter à Discord » et choisis ton serveur.": "Click \"Add to Discord\" and pick your server.",
  "Lance l'assistant": "Run the wizard",
  "Dans le panel, choisis le type de serveur (gaming, communauté, pro, streamer) et les fonctions voulues.": "In the dashboard, pick your server type (gaming, community, pro, streamer) and the features you want.",
  "C'est prêt": "You're set",
  "Le bot crée les salons et les rôles qui manquent et publie les panneaux. Tout reste modifiable ensuite.": "The bot creates missing channels and roles and posts the panels. Everything can be changed afterwards.",
  "Questions fréquentes": "FAQ", "Le bot est-il gratuit ?": "Is the bot free?",
  "Oui : la grande majorité des fonctions sont gratuites. La version Premium, par serveur, ajoute des modules avancés.": "Yes: most features are free. The Premium version, per server, adds advanced modules.",
  "Voir la comparaison": "See the comparison", "Faut-il savoir coder ?": "Do I need to code?",
  "Non. Tout se règle depuis le panel web, avec un aperçu en direct de chaque message et un assistant qui configure le serveur pour toi.": "No. Everything is set up from the web dashboard, with a live preview of each message and a wizard that sets up your server for you.",
  "Quelles permissions demande le bot ?": "Which permissions does the bot need?",
  "Il demande les droits d'administrateur pour pouvoir créer les salons et rôles, modérer et protéger le serveur. Pense à placer son rôle en haut de la liste des rôles.": "It asks for administrator rights to create channels and roles, moderate and protect the server. Remember to move its role to the top of the role list.",
  "Le bot parle-t-il anglais ?": "Does the bot speak English?",
  "Oui. La langue se choisit pour chaque serveur dans le panel, et le site et le panel ont un bouton FR / EN.": "Yes. The language is chosen per server in the dashboard, and the site and dashboard have an FR / EN button.",
  "Que deviennent mes données ?": "What happens to my data?",
  "Le bot ne garde que ce qui est nécessaire aux modules activés, et le contenu des messages n'est pas enregistré sauf options précises. Tout est détaillé dans la": "The bot only keeps what the enabled modules need, and message content is not stored except for specific options. Everything is detailed in the",
  "politique de confidentialité": "privacy policy", "Le bot est-il en ligne ?": "Is the bot online?",
  "L'état du bot en direct (en ligne, latence) est affiché sur la page": "The bot's live status (online, latency) is shown on the",
  "💎 Gratuit ou Premium": "💎 Free or Premium",
  "La version gratuite suffit à la plupart des serveurs. Premium s'active par serveur et débloque les modules avancés, sans redémarrage.": "The free version is enough for most servers. Premium is enabled per server and unlocks advanced modules, without a restart.",
  "Gratuit": "Free", "Pour toujours, sans carte bancaire.": "Forever, no credit card.", "Abonnement mensuel par serveur, géré par Discord.": "Monthly subscription per server, handled by Discord.",
  "Accueil, vérification, tickets, modmail": "Welcome, verification, tickets, modmail", "Niveaux, succès, quêtes, économie, mini-jeux": "Levels, achievements, quests, economy, mini-games",
  "Modération, automod, anti-raid, signalements": "Moderation, automod, anti-raid, reports", "Événements, tournois (16 joueurs), suggestions": "Events, tournaments (16 players), suggestions",
  "Panel web complet avec assistant de démarrage": "Full web dashboard with setup wizard",
  "Assistant IA, résumé de tickets, rédaction d'annonces": "AI assistant, ticket summaries, announcement drafting",
  "IA incluse, sans clé à fournir (FAQ, résumé de tickets, annonces)": "Built-in AI, no key needed (FAQ, ticket summaries, announcements)",
  "Assistant IA avec ta propre clé (ChatGPT, Mistral, Gemini, Claude)": "AI assistant with your own key (ChatGPT, Mistral, Gemini, Claude)",
  "IA incluse, sans clé": "Built-in AI, no key",
  "💳 Premium avec Patreon": "💳 Premium with Patreon",
  "💳 S'abonner sur Patreon": "💳 Subscribe on Patreon",
  "Délier mon compte Patreon": "Unlink my Patreon account",
  "Délier ton compte Patreon ? Le serveur qui profite de ton abonnement perdra Premium.": "Unlink your Patreon account? The server using your membership will lose Premium.",
  "Compte Patreon délié.": "Patreon account unlinked.",
  "Abonne-toi sur Patreon (mensuel ou annuel), puis relie ton compte : le Premium s'active sur ce serveur.": "Subscribe on Patreon (monthly or yearly), then link your account: Premium turns on for this server.",
  "🔗 Relier mon compte Patreon": "🔗 Link my Patreon account",
  "Abonnement trouvé !": "Membership found!",
  "Toujours aucun abonnement actif.": "Still no active membership.",
  "💎 Ton abonnement Patreon rend ce serveur Premium. Merci !": "💎 Your Patreon membership makes this server Premium. Thank you!",
  "Retirer de ce serveur": "Remove from this server",
  "Retirer ton Premium de ce serveur ? Tu ne pourras le mettre sur un autre serveur que dans 7 jours.": "Remove your Premium from this server? You can only move it to another server in 7 days.",
  "Premium retiré de ce serveur.": "Premium removed from this server.",
  "Un abonnement = un serveur Premium (changement possible une fois par semaine).": "One membership = one Premium server (can be moved once a week).",
  "💎 Utiliser mon Premium ici à la place": "💎 Use my Premium here instead",
  "💎 Activer Premium sur ce serveur": "💎 Activate Premium on this server",
  "💎 Premium activé sur ce serveur !": "💎 Premium activated on this server!",
  " (abonnement Patreon)": " (Patreon membership)",
  "Abonnement par serveur, mensuel ou annuel.": "Per-server subscription, monthly or yearly.",
  "Ensuite, ouvre le panel → ton serveur → 💎 Premium → « Relier mon compte Patreon » : le serveur passe Premium tout de suite.": "Then open the dashboard → your server → 💎 Premium → \"Link my Patreon account\": the server becomes Premium right away.",
  "a activé Premium avec Patreon": "activated Premium with Patreon",
  "a retiré son Premium Patreon": "removed their Patreon Premium",
  "Contact": "Contact",
  "📬 Nous contacter": "📬 Contact us",
  "Un module ne marche pas, une idée pour le bot, une question ? Chaque message est lu par le créateur du bot.": "A module isn't working, an idea for the bot, a question? Every message is read by the bot's creator.",
  "E-mail": "Email",
  "📋 Copier": "📋 Copy",
  "Copier": "Copy",
  "Copié": "Copied",
  "Un module ne marche pas": "A module isn't working",
  "Dis-nous quel module, ce que tu as fait et ce qui s'est passé. Une capture d'écran aide beaucoup.": "Tell us which module, what you did and what happened. A screenshot helps a lot.",
  "✉️ Signaler un bug": "✉️ Report a bug",
  "Une idée": "An idea",
  "Un module, une commande ou une option qui te manque ? Toutes les idées sont lues.": "A module, a command or an option you're missing? Every idea is read.",
  "✉️ Proposer une idée": "✉️ Suggest an idea",
  "Autre chose": "Something else",
  "Premium, données personnelles, partenariat ou simple question.": "Premium, personal data, partnership or just a question.",
  "✉️ Écrire un e-mail": "✉️ Write an email",
  "Depuis Discord, sans e-mail": "From Discord, no email needed",
  "Tape": "Type",
  "dans n'importe quel serveur où se trouve le bot, choisis 🐛, 💡 ou ✉️ et remplis le petit formulaire : le message arrive directement au créateur, qui peut te répondre en message privé.": "in any server the bot is on, choose 🐛, 💡 or ✉️ and fill in the short form: the message goes straight to the creator, who can reply by direct message.",
  "Un module ne marche pas : comment vous prévenir ?": "A module isn't working: how do I let you know?",
  "dans Discord ou passe par la page": "in Discord or use the",
  ": chaque message est lu par le créateur du bot.": "page: every message is read by the bot's creator.",
  "Un souci ou une idée ?": "A problem or an idea?",
  "Un module ne marche pas, une fonction te manque ? Écris-nous : tous les messages sont lus.": "A module isn't working, a feature is missing? Write to us: every message is read.",
  "Un module ne marche pas, une idée ? Écris-nous": "A module isn't working, an idea? Write to us",
  "📬 Contact": "📬 Contact",
  "Prévenir avant la fermeture auto": "Warn before auto-close",
  "Le membre est mentionné dans le ticket peu avant (jusqu'à 12 h avant) : un nouveau message annule la fermeture.": "The member is mentioned in the ticket shortly before (up to 12 h before): a new message cancels the closing.",
  "Relance si personne ne prend en charge (minutes)": "Reminder if nobody claims it (minutes)",
  "Le rôle Staff est mentionné dans le ticket et un message part dans les logs des tickets. 0 = jamais.": "The Staff role is mentioned in the ticket and a message goes to the ticket logs. 0 = never.",
  "Réponses enregistrées": "Saved replies",
  "Le staff les envoie avec /ticket reponse (la liste s'affiche en tapant). Variables : {user} (le membre), {staff} (toi), {number} (n° du ticket). 5 réponses (💎 50).": "Staff sends them with /ticket reponse (the list shows while typing). Variables: {user} (the member), {staff} (you), {number} (ticket no.). 5 replies (💎 50).",
  "➕ Ajouter une réponse": "➕ Add a reply",
  "Commandes du chat": "Chat commands", "➕ Ajouter une commande": "➕ Add a command",
  "Quand quelqu'un écrit la commande dans le chat Twitch, le bot répond. Variables : {user} (pseudo), {channel} (chaîne). 5 commandes (💎 50).": "When someone types the command in the Twitch chat, the bot replies. Variables: {user} (name), {channel} (channel). 5 commands (💎 50).",
  "Délai entre deux réponses (secondes)": "Delay between two replies (seconds)",
  "Pour une même commande, évite que le bot réponde en boucle.": "For the same command, stops the bot from replying over and over.",
  "Modération Twitch": "Twitch moderation",
  "Le bot modère le chat de ta chaîne Twitch et écrit chaque sanction dans un salon Discord, avec des boutons pour débannir ou bannir sans ouvrir Twitch. Le streamer, les modos et les VIP ne sont jamais sanctionnés.": "The bot moderates your Twitch chat and logs every action in a Discord channel, with buttons to unban or ban without opening Twitch. The streamer, mods and VIPs are never punished.",
  "Salon du journal Twitch": "Twitch log channel",
  "Vide = salon des logs de modération.": "Empty = moderation log channel.",
  "— Salon des logs de modération —": "— Moderation log channel —",
  "Liens d'arnaque": "Scam links",
  "Plus de 20 000 sites d'arnaque connus, et leurs imitations.": "Over 20,000 known scam sites, and their look-alikes.",
  "Liste des mots interdits": "Banned word list",
  "Un mot ou une expression par ligne (majuscules ignorées).": "One word or phrase per line (case ignored).",
  "Liens": "Links",
  "Tous les liens, sauf les sites autorisés ci-dessous.": "All links, except the allowed sites below.",
  "Un domaine par ligne (ex : twitch.tv). Les sous-domaines sont inclus.": "One domain per line (e.g. twitch.tv). Subdomains included.",
  "Majuscules : longueur minimum": "Caps: minimum length",
  "Les messages plus courts (en lettres) sont ignorés.": "Shorter messages (in letters) are ignored.",
  "Majuscules : pourcentage": "Caps: percentage",
  "À partir de ce pourcentage de lettres en majuscules.": "From this percentage of uppercase letters.",
  "Message répété": "Repeated message",
  "Le même message plusieurs fois en une minute.": "The same message several times within a minute.",
  "Répétitions avant sanction": "Repeats before action",
  "Durée du timeout (minutes)": "Timeout length (minutes)",
  "Pour l'automod et le bouton Timeout du journal (max 14 jours).": "For the automod and the log's Timeout button (max 14 days).",
  "Prévenir dans le chat": "Warn in chat",
  "Le bot écrit « @pseudo message retiré (raison) » après une suppression ou un timeout.": "The bot writes \"@name message removed (reason)\" after a deletion or timeout.",
  "Ne pas sanctionner les abonnés": "Don't punish subscribers",
  "Désactivé": "Off",
  "Supprimer le message": "Delete the message",
  "Bannir": "Ban",
  "🔗 Chaînes Twitch": "🔗 Twitch channels",
  "Le compte Twitch du bot n'est pas encore connecté par le propriétaire du bot.": "The bot's Twitch account is not connected by the bot owner yet.",
  "🤖 Connecter le compte Twitch du bot (propriétaire)": "🤖 Connect the bot's Twitch account (owner)",
  "Changer de compte (propriétaire)": "Change account (owner)",
  "Aucune chaîne reliée pour l'instant.": "No channel linked yet.",
  "✅ le bot est modérateur": "✅ the bot is a moderator",
  "❔ statut de modérateur inconnu": "❔ moderator status unknown",
  " · inactive (limite gratuite : 1 chaîne)": " · inactive (free limit: 1 channel)",
  "Délier": "Unlink",
  "🟣 Connecter ma chaîne Twitch": "🟣 Connect my Twitch channel",
  "Connecte-toi avec le compte Twitch du streamer. Ensuite, tape /mod suivi du nom du bot dans le chat pour qu'il puisse modérer.": "Log in with the streamer's Twitch account. Then type /mod followed by the bot's name in the chat so it can moderate.",
  "✅ Clé testée : choisis le modèle puis enregistre": "✅ Key tested: pick the model, then save",
  "🔑 Ton IA": "🔑 Your AI", "Fournisseur": "Provider", "Clé d'API": "API key", "Modèle": "Model",
  "🔌 Tester la clé": "🔌 Test the key", "💾 Enregistrer cette IA": "💾 Save this AI", "🗑️ Supprimer ma clé": "🗑️ Delete my key",
  "Créer ma clé →": "Create my key →", "Colle ta clé d'API ici": "Paste your API key here",
  "Aucune IA branchée pour l'instant.": "No AI connected yet.",
  "Branche ta propre IA : c'est gratuit avec le bot, tu paies seulement ton fournisseur (certains ont une offre gratuite). Ta clé est chiffrée et n'est jamais réaffichée.":
    "Connect your own AI: it's free with the bot, you only pay your provider (some have a free tier). Your key is encrypted and never shown again.",
  "Ne la partage jamais ailleurs. Un abonnement (ChatGPT Plus, Claude Pro…) ne suffit pas : il faut une clé d'API.":
    "Never share it anywhere else. A subscription (ChatGPT Plus, Claude Pro…) is not enough: you need an API key.",
  "Les modèles « mini », « flash » ou « small » sont plus rapides et moins chers.": "\"mini\", \"flash\" or \"small\" models are faster and cheaper.",
  "Aucune clé : l'IA incluse avec Premium répond. Tu peux brancher la tienne à la place.": "No key: the AI included with Premium answers. You can connect yours instead.",
  "Pour que l'assistant réponde, branche ton IA ci-dessous (gratuit) ou passe en 💎 Premium pour l'IA incluse.":
    "For the assistant to answer, connect your AI below (free) or upgrade to 💎 Premium for the built-in AI.",
  "Alertes Twitch, YouTube, Kick, TikTok et RSS": "Twitch, YouTube, Kick, TikTok and RSS alerts", "Giveaways, sondages, casino, quête de la semaine": "Giveaways, polls, casino, weekly quest",
  "Personnalisation complète, carte de bienvenue, captcha": "Full customization, welcome card, captcha",
  "Anti-nuke, accès au panel par rôle, statistiques 90 jours": "Anti-nuke, role-based dashboard access, 90-day statistics",
  "Dans Discord : tape": "In Discord: type", "sur ton serveur.": "on your server.", "Fonction": "Feature",
  "👋 Accueil": "👋 Welcome", "Bienvenue, au revoir, message privé": "Welcome, goodbye, DM", "Textes par défaut": "Default texts", "Textes personnalisés": "Custom texts",
  "Carte de bienvenue en image": "Welcome image card", "Vérification par bouton": "Button verification", "Captcha anti-robot": "Anti-bot captcha",
  "Menus de rôles": "Role menus", "Suivi des invitations et parrainage": "Invite tracking and referrals", "Tickets, modmail, priorités": "Tickets, modmail, priorities",
  "Formulaire par type de ticket": "Form per ticket type", "Transcript HTML et avis ⭐": "HTML transcript and ⭐ feedback", "Niveaux et classement": "Levels and leaderboard",
  "XP vocal, carte de rang, classements semaine / mois": "Voice XP, rank card, weekly / monthly leaderboards", "Succès, quêtes du jour, séries": "Achievements, daily quests, streaks",
  "Économie et banque": "Economy and bank", "Intérêts 1 %": "1% interest", "Taux réglable": "Adjustable rate", "Boutique, nom et emoji de la monnaie": "Shop, currency name and emoji",
  "Mini-jeux": "Mini-games", "✅ + casino": "✅ + casino", "Événements": "Events", "Tournois": "Tournaments", "16 joueurs": "16 players", "64 joueurs": "64 players",
  "Giveaways et sondages": "Giveaways and polls", "Rappels actifs par membre": "Active reminders per member", "🛡️ Modération": "🛡️ Moderation",
  "Automod, liens d'arnaque, anti-raid, signalements": "Automod, scam links, anti-raid, reports", "Anti-nuke et lockdown automatique": "Anti-nuke and automatic lockdown",
  "7 jours": "7 days", "30 jours": "30 days", "📺 Outils": "📺 Tools", "Assistant IA (FAQ, résumé, annonces)": "AI assistant (FAQ, summaries, announcements)",
  "⚙️ Panel": "⚙️ Dashboard", "Couleur et pied de page des messages": "Message color and footer", "Statistiques en graphiques": "Statistics charts",
  "7, 30 et 90 jours": "7, 30 and 90 days", "Accès au panel par rôle": "Dashboard access by role",
  "📚 Toutes les commandes": "📚 All commands", "Chargement…": "Loading…", "Rechercher une commande (ex : ticket, banque, warn)…": "Search a command (e.g. ticket, bank, warn)…",
  "Tout": "All", "Staff": "Staff", "Aucune commande ne correspond.": "No command matches.", "Impossible de charger les commandes.": "Couldn't load the commands.",
  "Rappels & anniversaires": "Reminders & birthdays", "Suggestions & communauté": "Suggestions & community", "Vocaux temporaires": "Temporary voice",
  "Configuration": "Configuration", "Commandes perso": "Custom commands", "Autres": "Other",
  "📡 Statut du bot": "📡 Bot status", "Mis à jour automatiquement toutes les 30 secondes.": "Updated automatically every 30 seconds.", "Vérification…": "Checking…",
  "latence Discord": "Discord latency", "en ligne depuis": "online for", "modules chargés": "loaded modules", "version": "version",
  "En ligne": "Online", "Le bot redémarre ou est déconnecté de Discord": "The bot is restarting or disconnected from Discord",
  "Hors ligne : le serveur ne répond pas": "Offline: the server isn't responding", "Dernière vérification": "Last check",
  // panel
  "Démarrage": "Getting started", "Support & IA": "Support & AI", "Outils": "Tools", "Gestion": "Management", "Nouveautés": "What's new", "Nouveau": "New",
  "🔎 Rechercher un réglage…": "🔎 Search a setting…", "Changer de serveur": "Switch server", "Résultats de recherche": "Search results",
  "Aucun réglage ne correspond. Essaie un autre mot (ex : bienvenue, ticket, xp, logs).": "No setting matches. Try another word (e.g. welcome, ticket, xp, logs).",
  "Modifications non enregistrées": "Unsaved changes", "↺ par défaut": "↺ default", "Remettre la valeur par défaut": "Reset to default",
  "🧪 Tester dans Discord": "🧪 Test in Discord", "🧪 M'envoyer le test en MP": "🧪 Send me the test by DM",
  "Enregistre d'abord tes modifications : le test utilise la configuration enregistrée.": "Save your changes first: the test uses the saved configuration.",
  "✅ Test envoyé en message privé.": "✅ Test sent by DM.", "Rien à enregistrer.": "Nothing to save.",
  "Ce qui a été ajouté au bot, version par version.": "What was added to the bot, version by version.",
  "✅ Configuration terminée": "✅ Setup complete",
  "Me donner les permissions « Gérer les rôles » et « Gérer les salons »": "Give me the \"Manage Roles\" and \"Manage Channels\" permissions",
  "Paramètres du serveur → Rôles": "Server Settings → Roles", "Choisir le rôle Staff": "Choose the Staff role", "Choisir un salon de logs (privé)": "Choose a (private) log channel",
  "Choisir le salon de bienvenue": "Choose the welcome channel", "Configurer la vérification (salon des règles + rôle Membre)": "Set up verification (rules channel + Member role)",
  "Configurer les tickets (catégorie + salon du panneau)": "Set up tickets (category + panel channel)",
  "Publier les panneaux (règles, notifications, tickets)": "Post the panels (rules, notifications, tickets)", "Activer l'automod": "Enable automod",
  "Régler →": "Set up →", "Publier →": "Post →",
  "Panel et site plus pratiques": "Handier dashboard and site", "Menu par catégories et recherche dans tous les réglages": "Menu by category and search across all settings",
  "Checklist de configuration avec barre de progression": "Setup checklist with progress bar", "Boutons « Tester dans Discord » et « ↺ par défaut »": "\"Test in Discord\" and \"↺ default\" buttons",
  "Thème clair / sombre, changement rapide de serveur, Ctrl+S pour enregistrer": "Light / dark theme, quick server switch, Ctrl+S to save",
  "Site : nouvelles pages Commandes, Premium et Statut": "Site: new Commands, Premium and Status pages",
  "Événements, IA et modération avancée": "Events, AI and advanced moderation", "Événements avec inscription et rappel, tournois à élimination directe": "Events with sign-up and reminder, single-elimination tournaments",
  "Parrainage récompensé": "Rewarded referrals", "💎 Assistant IA : FAQ, résumé de ticket, rédaction d'annonces": "💎 AI assistant: FAQ, ticket summary, announcement drafting",
  "Signalements par clic droit, ralenti automatique, journal des messages": "Right-click reports, automatic slow mode, message log",
  "Engagement et staff": "Engagement and staff", "19 succès, quêtes du jour (💎 quête de la semaine), séries d'activité, banque": "19 achievements, daily quests (💎 weekly quest), activity streaks, bank",
  "Activité du staff et /modstats par période": "Staff activity and /modstats by period", "💎 Accès au panel par rôle": "💎 Dashboard access by role",
  "💎 Alertes Kick, TikTok et RSS": "💎 Kick, TikTok and RSS alerts", "Sécurité et prise en main": "Security and onboarding",
  "Avertissements qui expirent, blocage des liens d'arnaque": "Expiring warnings, scam link blocking", "Modmail, suivi des invitations": "Modmail, invite tracking",
  "💎 Formulaires de ticket": "💎 Ticket forms", "Modèles de configuration et assistant de démarrage": "Configuration templates and setup wizard",
  "Vocaux temporaires, suggestions, starboard": "Temporary voice, suggestions, starboard", "Compteurs, commandes perso, menus de rôles": "Counters, custom commands, role menus",
  "Messages programmés et sauvegarde de la configuration": "Scheduled messages and configuration backup", "Jeux et aperçu": "Games and preview",
  "Mini-jeux et casino": "Mini-games and casino", "Aperçu en direct des messages": "Live message preview", "Bot entièrement disponible en anglais": "Bot fully available in English",
  "Économie et statistiques": "Economy and statistics", "Économie et boutique": "Economy and shop", "Rappels et anniversaires": "Reminders and birthdays",
  "Statistiques en graphiques et historique du panel": "Statistics charts and dashboard history",
  "Thème sombre": "Dark theme", "Thème clair": "Light theme",
  "Tu dois être membre du serveur pour recevoir le test.": "You must be a member of the server to receive the test.",
  "Choisis d'abord le salon (et enregistre), puis relance le test.": "Pick the channel first (and save), then run the test again.",
  "Attends quelques secondes entre deux tests.": "Wait a few seconds between two tests.", "Le message est vide.": "The message is empty.",
  "Le message privé est vide.": "The DM is empty.", "Je ne peux pas t'écrire en privé : ouvre tes messages privés pour ce serveur.": "I can't DM you: open your DMs for this server.",
  // --- v13 : événements, tournois, IA, signalements, journal des messages
  "Événements & tournois": "Events & tournaments",
  "Événements avec inscription et rappel (/evenement creer), tournois à élimination directe avec tableau tiré au sort (/tournoi creer, lancer, resultat). 16 joueurs en gratuit, 💎 64 en Premium.":
    "Events with sign-up and reminder (/evenement creer), single-elimination tournaments with a random bracket (/tournoi creer, lancer, resultat). 16 players free, 💎 64 with Premium.",
  "Activer les événements et tournois": "Enable events and tournaments", "Rôle gestionnaire": "Manager role",
  "Peut créer et gérer les événements et tournois (en plus de « Gérer le serveur »).": "Can create and manage events and tournaments (on top of \"Manage Server\").",
  "Rappel avant le début (minutes)": "Reminder before start (minutes)",
  "Les inscrits sont mentionnés dans le salon de l'événement.": "Attendees are mentioned in the event's channel.",
  "Assistant IA": "AI assistant",
  "Le bot répond aux questions des membres à partir de tes règles et de ta FAQ (/ia, salon dédié ou mention), résume les tickets pour le staff (/resume-ticket) et rédige des annonces (/annonce-ia).":
    "The bot answers members' questions from your rules and FAQ (/ia, a dedicated channel or a mention), summarizes tickets for the staff (/resume-ticket) and drafts announcements (/annonce-ia).",
  "Activer l'assistant IA": "Enable the AI assistant", "FAQ et informations du serveur": "Server FAQ and information",
  "Tout ce que l'IA doit savoir : horaires, liens, comment devenir staff, IP du serveur de jeu… 8 000 caractères max. Les règles (onglet Vérification) sont ajoutées automatiquement.":
    "Everything the AI should know: schedules, links, how to join the staff, game server IP… 8,000 characters max. The rules (Verification tab) are added automatically.",
  "Salon d'aide IA": "AI help channel", "Le bot répond à toutes les questions posées dans ce salon. Facultatif.": "The bot answers every question asked in this channel. Optional.",
  "Répondre quand on mentionne le bot": "Answer when the bot is mentioned", "Dans n'importe quel salon.": "In any channel.",
  "Questions maximum par jour": "Maximum questions per day", "Pour tout le serveur (1 à 1000).": "For the whole server (1 to 1000).",
  "L'assistant IA n'est pas encore activé sur ce bot : le propriétaire doit ajouter une clé d'API Claude (ANTHROPIC_API_KEY).":
    "The AI assistant isn't enabled on this bot yet: the owner must add a Claude API key (ANTHROPIC_API_KEY).",
  "Signalements": "Reports",
  "Clic droit sur un message → Applications → « Signaler le message ». Le staff reçoit le signalement avec des boutons (supprimer, muter 10 min, traité). /signalements liste ceux en attente.":
    "Right-click a message → Apps → \"Report message\". The staff gets the report with buttons (delete, mute 10 min, handled). /signalements lists pending ones.",
  "Salon des signalements": "Reports channel", "Vide = logs de modération.": "Empty = moderation logs.", "— Logs de modération —": "— Moderation logs —",
  "Journal des messages": "Message log",
  "Garde les messages modifiés et supprimés pour les consulter dans l'onglet « Journal des messages ». Désactivé = rien n'est gardé.":
    "Keeps edited and deleted messages to view them in the \"Message log\" tab. Disabled = nothing is kept.",
  "Durée de conservation (jours)": "Retention (days)",
  "7 jours en gratuit, jusqu'à 30 en Premium. Les messages plus anciens sont effacés automatiquement.": "7 days free, up to 30 with Premium. Older messages are deleted automatically.",
  "Ralenti automatique": "Automatic slow mode",
  "Si un salon s'emballe, le mode lent s'active quelques minutes puis se retire tout seul.": "If a channel gets flooded, slow mode turns on for a few minutes then turns off by itself.",
  "Messages en 10 secondes avant ralenti": "Messages in 10 seconds before slow mode", "Délai du mode lent (secondes)": "Slow mode delay (seconds)",
  "Durée du ralenti (minutes)": "Slow mode duration (minutes)",
  "Récompense de parrainage": "Referral reward",
  "Argent donné à celui qui invite quand son invité reste assez longtemps. 0 = désactivé.": "Money given to the inviter when their invitee stays long enough. 0 = disabled.",
  "… après combien de jours": "… after how many days", "Évite les faux comptes qui rejoignent puis repartent.": "Prevents fake accounts that join then leave.",
  "🕵️ Journal des messages": "🕵️ Message log",
  "Les messages modifiés et supprimés (200 derniers), gardés le temps choisi dans l'onglet Modération puis effacés automatiquement.":
    "Edited and deleted messages (last 200), kept for the time chosen in the Moderation tab then deleted automatically.",
  "Tous les salons": "All channels", "Modifiés et supprimés": "Edited and deleted", "✏️ Modifiés": "✏️ Edited", "🗑️ Supprimés": "🗑️ Deleted",
  "ID du membre": "Member ID", "Rechercher un mot…": "Search a word…", "Aller au message": "Go to message",
  "Le journal est désactivé : active-le dans l'onglet Modération (rien n'est enregistré tant qu'il est désactivé).":
    "The log is disabled: turn it on in the Moderation tab (nothing is recorded while it's off).",
  "Aucun message dans le journal pour ces filtres.": "No message in the log for these filters.",
  "Répond aux questions des membres avec ta FAQ, résume les tickets et rédige tes annonces.": "Answers members' questions with your FAQ, summarizes tickets and drafts your announcements.",
  "IA incluse": "Built-in AI",
  "Sans clé à fournir : répond aux questions avec ta FAQ, résume les tickets et rédige tes annonces.": "No key needed: answers questions with your FAQ, summarizes tickets and drafts your announcements.",
  // --- v12 : engagement, banque, alertes, accès au panel, staff
  "Succès & quêtes": "Achievements & quests",
  "Fait revenir les membres : 19 succès à débloquer (badges + récompenses), 3 quêtes par jour, séries d'activité. Commandes : /profil, /succes, /quetes.":
    "Keeps members coming back: 19 achievements to unlock (badges + rewards), 3 quests per day, activity streaks. Commands: /profil, /succes, /quetes.",
  "Activer l'engagement": "Enable engagement", "Succès et badges": "Achievements and badges",
  "Messages, niveaux, fortune, séries, invitations, quêtes, mini-jeux. Chaque succès donne une récompense.":
    "Messages, levels, wealth, streaks, invites, quests, mini-games. Each achievement gives a reward.",
  "Quêtes du jour": "Daily quests", "3 quêtes tirées au sort chaque jour (les mêmes pour tout le serveur).": "3 random quests every day (the same for the whole server).",
  "Récompense par quête du jour": "Reward per daily quest", "Quête de la semaine": "Weekly quest",
  "Une quête plus difficile, renouvelée chaque lundi.": "A harder quest, renewed every Monday.",
  "Récompense de la quête de la semaine": "Weekly quest reward", "Annoncer les succès et quêtes terminées": "Announce achievements and completed quests",
  "Salon des annonces": "Announcement channel",
  "Vide = dans le salon de l'action (message effacé après 1 minute).": "Empty = in the channel where it happened (message deleted after 1 minute).",
  "Banque": "Bank", "/banque deposer et /banque retirer : l'argent placé rapporte des intérêts chaque jour.":
    "/banque deposer and /banque retirer: money in the bank earns interest every day.",
  "Intérêts par jour (%)": "Daily interest (%)", "Entre 0 et 10 %. Version gratuite : 1 %.": "Between 0 and 10%. Free version: 1%.",
  "Plafond de la banque": "Bank limit", "Au-delà, plus de dépôt ni d'intérêts. 0 = pas de plafond.": "Above it, no more deposits or interest. 0 = no limit.",
  "Alertes": "Alerts",
  "Annonce automatique des lives, des nouvelles vidéos et des articles (vérification toutes les 3 minutes). Variables : {name} {title} {url} {game}. Tu peux mettre @everyone ou mentionner un rôle dans le message.":
    "Automatic announcements of streams, new videos and articles (checked every 3 minutes). Variables: {name} {title} {url} {game}. You can put @everyone or mention a role in the message.",
  "Chaînes Kick": "Kick channels", "Le pseudo tel qu'il apparaît dans kick.com/pseudo": "The username as shown in kick.com/username",
  "Comptes TikTok": "TikTok accounts",
  "Lives (toutes les 3 min) et nouvelles vidéos (toutes les 15 min). TikTok n'a pas d'API publique : fonctionne via le site, peut parfois être en retard.":
    "Lives (every 3 min) and new videos (every 15 min). TikTok has no public API: works through the website, may sometimes be late.",
  "Flux RSS": "RSS feeds",
  "Sites d'actu, blogs, patch notes de jeux… Tout flux RSS ou Atom public. Variables : {name} (nom du site) {title} {url}":
    "News sites, blogs, game patch notes… Any public RSS or Atom feed. Variables: {name} (site name) {title} {url}",
  "Pseudo Kick (ex : kick.com/pseudo)": "Kick username (e.g. kick.com/username)", "➕ Ajouter une chaîne Kick": "➕ Add a Kick channel",
  "@pseudo TikTok": "TikTok @username", "Message des lives (vide = par défaut)": "Live message (empty = default)",
  "➕ Ajouter un compte TikTok": "➕ Add a TikTok account", "Adresse du flux (https://…/rss.xml)": "Feed address (https://…/rss.xml)",
  "➕ Ajouter un flux RSS": "➕ Add an RSS feed",
  "Accès au panel": "Dashboard access",
  "Donne à certains rôles (ex : Modérateurs) un accès limité au panel, sans leur donner « Gérer le serveur ». Ils ne voient et ne modifient que les parties cochées. Les admins ont toujours accès à tout.":
    "Give some roles (e.g. Moderators) limited dashboard access without giving them \"Manage Server\". They only see and edit the ticked parts. Admins always have full access.",
  "Rôles autorisés": "Allowed roles",
  "10 rôles maximum. La création automatique, les modèles, la sauvegarde et cet onglet restent réservés aux admins.":
    "10 roles maximum. Auto-setup, templates, backup and this tab stay admin-only.",
  "— Choisir un rôle —": "— Choose a role —", "➕ Ajouter un rôle": "➕ Add a role",
  "Communauté": "Community", "Tickets & modmail": "Tickets & modmail", "Alertes & événements": "Alerts & events", "Statistiques": "Statistics",
  "👮 Accès limité": "👮 Limited access", "Accès limité": "Limited access",
  "Un admin t'a donné accès à une partie du panel. Tu peux modifier :": "An admin gave you access to part of the dashboard. You can edit:",
  "Ton rôle n'a pas accès à cette partie du panel (réservé aux admins).": "Your role can't access this part of the dashboard (admins only).",
  "👮 Activité du staff": "👮 Staff activity", "Membre du staff": "Staff member", "Total": "Total", "Sanctions": "Punishments", "Notes": "Notes",
  "Aucune activité du staff sur cette période.": "No staff activity in this period.",
  "Alertes Kick, TikTok et RSS": "Kick, TikTok and RSS alerts",
  "Lives Kick et TikTok, nouvelles vidéos TikTok, articles de n'importe quel site.": "Kick and TikTok lives, new TikTok videos, articles from any website.",
  "Une grosse quête chaque semaine en plus des 3 quêtes du jour, et intérêts de banque réglables.": "A big quest every week on top of the 3 daily quests, and adjustable bank interest.",
  "Accès au panel par rôle": "Dashboard access by role",
  "Tes modérateurs gèrent leur partie du panel sans avoir « Gérer le serveur ».": "Your moderators manage their part of the dashboard without \"Manage Server\".",
  // --- v11 : modmail, invitations, liens dangereux, modèles, assistant
  "Modmail & invitations": "Modmail & invites",
  "Modmail : un membre écrit au bot en message privé, une conversation s'ouvre dans un salon privé du staff (catégorie des tickets). Invitations : le bot retient qui a invité qui (/invitations voir, /invitations classement).":
    "Modmail: a member DMs the bot and a conversation opens in a private staff channel (ticket category). Invites: the bot remembers who invited whom (/invitations voir, /invitations classement).",
  "Activer le modmail": "Enable modmail", "Nécessite la catégorie des tickets (onglet Tickets).": "Requires the ticket category (Tickets tab).",
  "Réponses anonymes du staff": "Anonymous staff replies", "Le membre voit « Staff de serveur » au lieu du pseudo.": "The member sees “Server staff” instead of the username.",
  "Message de confirmation": "Confirmation message", "Envoyé au membre à l'ouverture. {server} {name}": "Sent to the member when opened. {server} {name}",
  "Suivre les invitations": "Track invites", "Il me faut la permission « Gérer le serveur » pour lire les invitations.": "I need the “Manage Server” permission to read invites.",
  "Salon des annonces d'invitation": "Invite announcement channel", "Facultatif : annonce qui a invité chaque nouveau membre.": "Optional: announces who invited each new member.",
  "Message d'annonce": "Announcement message",
  "Expiration des avertissements (jours)": "Warning expiry (days)",
  "Un avertissement plus ancien ne compte plus pour les sanctions automatiques. 0 = jamais.": "Older warnings no longer count toward automatic punishments. 0 = never.",
  "Bloquer les liens dangereux": "Block dangerous links",
  "Phishing, faux Nitro, faux Steam : liste de +20 000 arnaques connues + détection des imitations. Le compte qui l'envoie est mis en sourdine 10 min (souvent piraté).":
    "Phishing, fake Nitro, fake Steam: list of 20,000+ known scams + lookalike detection. The sender is muted for 10 min (often a hacked account).",
  "Sites autorisés": "Allowed sites", "Un domaine par ligne (ex : monsite.fr), jamais considéré comme dangereux.": "One domain per line (e.g. mysite.com), never treated as dangerous.",
  "💎 Questions du formulaire (séparées par |)": "💎 Form questions (separated by |)",
  "25 maximum. 💎 Premium : chaque type peut avoir son propre formulaire (jusqu'à 5 questions, séparées par |).": "25 maximum. 💎 Premium: each type can have its own form (up to 5 questions, separated by |).",
  "🪄 Lancer l'assistant": "🪄 Start the wizard", "Modèles de configuration": "Configuration templates",
  "Applique en un clic des réglages adaptés à ton type de serveur (textes, règles, types de tickets, modules activés). Tes salons et rôles déjà choisis sont conservés.":
    "Apply settings suited to your type of server in one click (texts, rules, ticket types, enabled modules). Channels and roles you already picked are kept.",
  "Appliquer": "Apply", "🎮 Gaming": "🎮 Gaming", "💬 Communauté": "💬 Community", "💼 Pro / École": "💼 Pro / School", "📺 Streamer / Créateur": "📺 Streamer / Creator",
  "Communauté de joueurs : niveaux, mini-jeux, économie, vocaux temporaires, alertes de stream.": "Gaming community: levels, mini-games, economy, temporary voice, stream alerts.",
  "Serveur de discussion : accueil chaleureux, suggestions, anniversaires, niveaux.": "Chat server: warm welcome, suggestions, birthdays, levels.",
  "Entreprise, association ou classe : sobre, sécurisé, tickets de support, pas de jeux.": "Company, association or class: clean, secure, support tickets, no games.",
  "Communauté d'un créateur : alertes de live et de vidéos, rôles de notification, giveaways.": "Creator community: stream and video alerts, notification roles, giveaways.",
  "Bienvenue dans l'assistant": "Welcome to the wizard",
  "En 4 étapes, ton serveur sera prêt : type de serveur, fonctions, création des salons et rôles, publication des panneaux.":
    "In 4 steps your server will be ready: server type, features, channels and roles, panels.",
  "1. Quel type de serveur ?": "1. What kind of server?", "Passer cette étape →": "Skip this step →", "Fermer": "Close",
  "Langue et fonctions": "Language and features", "Coche ce que tu veux activer (tout reste modifiable ensuite) :": "Tick what you want to enable (everything can be changed later):",
  "Enregistrer et continuer →": "Save and continue →", "Salons et rôles": "Channels and roles",
  "Je crée ce qui manque : règles, rôles, support, logs privés, catégorie Tickets, suggestions, rôles Staff / Membre / Non vérifié, notifications et niveaux. Rien n'est créé en double.":
    "I create what's missing: rules, roles, support, private logs, Tickets category, suggestions, Staff / Member / Unverified roles, notifications and levels. Nothing is duplicated.",
  "Passer →": "Skip →", "✨ Créer les salons et rôles": "✨ Create channels and roles", "Publier les panneaux": "Publish the panels",
  "Je poste le panneau des règles (avec le bouton de vérification), le menu des notifications et le panneau de tickets dans leurs salons.":
    "I post the rules panel (with the verification button), the notifications menu and the ticket panel in their channels.",
  "📤 Publier les panneaux": "📤 Publish the panels", "C'est prêt !": "All set!", "Terminer": "Finish",
  "Retire « Voir les salons » à @everyone et donne-la au rôle Membre : les nouveaux ne verront que les règles avant de se vérifier.":
    "Remove “View Channels” from @everyone and give it to the Member role: newcomers will only see the rules until they verify.",
  "Tout se règle ensuite dans les onglets du panel, avec aperçu en direct.": "Everything else is set in the dashboard tabs, with live preview.",
  "👋 Messages de bienvenue": "👋 Welcome messages", "📈 Niveaux et XP": "📈 Levels & XP", "💰 Économie": "💰 Economy", "🎮 Mini-jeux": "🎮 Mini-games",
  "🤖 Automod": "🤖 Automod", "🛡️ Anti-raid": "🛡️ Anti-raid", "🔊 Vocaux temporaires": "🔊 Temporary voice", "💡 Suggestions": "💡 Suggestions",
  "🎂 Anniversaires": "🎂 Birthdays", "📬 Modmail": "📬 Modmail", "a appliqué un modèle": "applied a template",

  "Mini-jeux": "Mini-games",
  "Jeux avec la monnaie du serveur : /pileouface, /des, /devine, /quiz. Casino 💎 : /roulette, /blackjack.": "Games using the server currency: /pileouface, /des, /devine, /quiz. 💎 Casino: /roulette, /blackjack.",
  "Activer les mini-jeux": "Enable mini-games", "Nécessite l'économie activée.": "Requires the economy to be enabled.",
  "Mise maximum": "Maximum bet", "Gain du /quiz": "/quiz reward", "Gain max de /devine": "Max /devine reward",
  "Diminue à chaque essai raté.": "Decreases with each wrong guess.",

  "👁️ Aperçu en direct": "👁️ Live preview", "👁️ Aperçu (version gratuite : texte par défaut)": "👁️ Preview (free version: default text)",
  "Aujourd'hui": "Today", "👋 Nouveau membre !": "👋 New member!", "Compte créé": "Account created", "Membre n°": "Member #",
  "il y a 2 ans": "2 years ago", "🎂 Joyeux anniversaire !": "🎂 Happy birthday!", "✅ J'accepte les règles": "✅ I accept the rules",
  "🔔 Rôles de notification": "🔔 Notification roles", "🔔 Choisis tes notifications…": "🔔 Choose your notifications…",
  "📩 Besoin d'aide ?": "📩 Need help?", "📩 Choisis le type de ticket…": "📩 Choose the ticket type…",

  // --- statistiques / historique
  "📊 Statistiques": "📊 Statistics", "L'évolution de ton serveur jour par jour.": "Your server's evolution day by day.",
  "arrivées": "joins", "départs": "leaves", "messages": "messages", "en vocal": "in voice", "👥 Membres": "👥 Members", "💬 Activité": "💬 Activity",
  "minutes en vocal": "voice minutes", "🎫 Tickets et modération": "🎫 Tickets & moderation",
  "Les statistiques sont collectées depuis l'arrivée de cette version du bot (dates en UTC).": "Statistics are collected since this bot version was installed (dates in UTC).",
  "Les statistiques sur 30 et 90 jours sont Premium 💎": "30 and 90-day statistics are Premium 💎",
  "📜 Historique du panel": "📜 Dashboard history", "Qui a modifié quoi dans le panel (100 dernières actions).": "Who changed what in the dashboard (last 100 actions).",
  "a modifié la configuration": "changed the settings", "a lancé la création automatique": "ran the automatic setup", "a publié les panneaux": "published the panels",
  "Aucune modification pour l'instant.": "No changes yet.",

  // --- premium
  "Ce serveur utilise la version gratuite. Les réglages 💎 sont enregistrés mais inactifs.": "This server uses the free version. 💎 settings are saved but inactive.",
  "💎 Passer à Premium": "💎 Upgrade to Premium",
  "Pour activer Premium, contacte le propriétaire du bot (ou tape /premium dans Discord).": "To enable Premium, contact the bot owner (or type /premium in Discord).",
  "💎 Ce serveur est Premium": "💎 This server is Premium", " (accès offert)": " (gifted access)", " (abonnement Discord)": " (Discord subscription)", ". Merci !": ". Thank you!",
  "Giveaways et sondages": "Giveaways & polls", "Concours avec tirage automatique, sondages à boutons avec résultats en direct.": "Giveaways with automatic draw, button polls with live results.",
  "Captcha de vérification": "Verification captcha", "Bloque les comptes robots avant qu'ils accèdent au serveur.": "Blocks bot accounts before they access the server.",
  "Niveaux avancés": "Advanced levels", "XP en vocal, carte de rang en image, classements de la semaine et du mois.": "Voice XP, image rank card, weekly and monthly leaderboards.",
  "Alertes Twitch et YouTube": "Twitch & YouTube alerts", "Annonce automatique des lives et des nouvelles vidéos.": "Automatic announcement of streams and new videos.",
  "Personnalisation complète": "Full customization", "Couleur, pied de page, messages de bienvenue, d'au revoir et de niveau.": "Color, footer, welcome, goodbye and level-up messages.",
  "Tickets avancés": "Advanced tickets", "Transcripts HTML et avis ⭐ après chaque ticket.": "HTML transcripts and ⭐ feedback after each ticket.",
  "Sécurité avancée": "Advanced security", "Anti-nuke, lockdown automatique en cas de raid, alertes au propriétaire.": "Anti-nuke, automatic raid lockdown, owner alerts.",
  "Économie et boutique": "Economy & shop",
};

// Textes avec des nombres ou des noms variables
const EN_PATTERNS = [
  [/^📋 Configuration : (\d+)\/(\d+)$/, "📋 Setup: $1/$2"],
  [/^✅ Test envoyé dans (.+)\.$/, "✅ Test sent to $1."],
  [/^Je ne peux pas écrire dans #(.+)\.$/, "I can't write in #$1."],
  [/^v(\d+) · $/, "v$1 · "],
  [/^Sur les (\d+) derniers jours : sanctions données, tickets pris en charge et notes écrites\. Aussi dans Discord avec \/modstats\.$/,
    "Over the last $1 days: punishments given, tickets claimed and notes written. Also in Discord with /modstats."],
  [/^Ancien membre \((\d+)\)$/, "Former member ($1)"],
  [/^⚠️ Dernière chose, dans Discord : Paramètres du serveur → Rôles, glisse mon rôle \(@(.+)\) tout en haut de la liste\.$/,
    "⚠️ One last thing, in Discord: Server Settings → Roles, drag my role (@$1) to the top of the list."],
  [/^✅ Modèle « (.+) » appliqué\.$/, "✅ Template “$1” applied."],
  [/^Appliquer le modèle « (.+) » \? Les textes et réglages correspondants seront remplacés\.$/, "Apply the “$1” template? The matching texts and settings will be replaced."],
  [/^➕ Créer un menu \((\d+)\/(\d+)\)$/, "➕ Create a menu ($1/$2)"],
  [/^✅ Message envoyé dans #(.+)$/, "✅ Message sent to #$1"],
  [/^✅ Menu publié dans #(.+)$/, "✅ Menu published in #$1"],
  [/^💎 Ce menu dépasse la limite de ta version \((\d+)\)\. Il ne fonctionnera qu'avec Premium\.$/, "💎 This menu exceeds your version's limit ($1). It will only work with Premium."],
  [/^(\d+) maximum\.$/, "$1 maximum."],
  [/^🩺 Diagnostic : (\d+) problème\(s\)$/, "🩺 Diagnostics: $1 issue(s)"],
  [/^(\d+) problème\(s\)$/, "$1 issue(s)"],
  [/^(\d+) jours$/, "$1 days"],
  [/^Créé :/, "Created:"],
  [/^Pense à placer mon rôle \(@(.+)\) tout en haut de la liste dans Paramètres du serveur → Rôles, sinon je ne pourrai pas donner les rôles\.$/,
    "Make sure my role (@$1) is at the top of the list in Server Settings → Roles, otherwise I can't give roles."],
  [/^ jusqu'au (.+)$/, " until $1"],
  [/^Salon de bienvenue : (.+)$/, "Welcome channel: $1"],
  [/^(.+) : non défini$/, "$1: not set"],
  [/^Toutes mes permissions sont présentes$/, "All my permissions are present"],
  [/^Compte Patreon relié(?: \((.+)\))?, mais aucun abonnement actif pour l'instant\. Si tu viens de payer, attends une minute puis actualise\.$/, "Patreon account linked, but no active membership yet. If you just paid, wait a minute then refresh."],
  [/^Ton abonnement est utilisé sur « (.+) »\. Un abonnement = un serveur Premium \(changement possible une fois par semaine\)\.$/, "Your membership is used on \"$1\". One membership = one Premium server (can be moved once a week)."],
  [/^Ton abonnement Patreon est actif\. Un abonnement = un serveur Premium \(changement possible une fois par semaine\)\.$/, "Your Patreon membership is active. One membership = one Premium server (can be moved once a week)."],
  [/^Changement de serveur possible à partir du (.+)\.$/, "Server change possible from $1."],
  [/^« (.+) » perdra Premium\. Continuer \?$/, "\"$1\" will lose Premium. Continue?"],
  [/^Permissions manquantes : (.+)$/, "Missing permissions: $1"],
];

function translateText(text) {
  if (LANG !== "en") return text;
  const trimmed = text.trim();
  if (!trimmed) return text;
  let out = EN[trimmed];
  if (out === undefined) {
    for (const [re, rep] of EN_PATTERNS) if (re.test(trimmed)) { out = trimmed.replace(re, rep); break; }
  }
  if (out === undefined) return text;
  return text.replace(trimmed, out);
}

function translateDom(root) {
  if (LANG !== "en" || !root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const next = translateText(node.data);
    if (next !== node.data) node.data = next;
  }
  const elements = root.querySelectorAll ? root.querySelectorAll("[placeholder],[title]") : [];
  for (const el of elements) {
    for (const attr of ["placeholder", "title"]) {
      const v = el.getAttribute(attr);
      if (v) { const t = translateText(v); if (t !== v) el.setAttribute(attr, t); }
    }
  }
}

// Traduit automatiquement tout ce qui s'ajoute à la page (rendu du panel, notifications…)
if (LANG === "en") {
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) for (const n of m.addedNodes) {
      if (n.nodeType === Node.TEXT_NODE) { const t = translateText(n.data); if (t !== n.data) n.data = t; }
      else if (n.nodeType === Node.ELEMENT_NODE) translateDom(n);
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    translateDom(document.body);
    document.title = translateText(document.title);
    observer.observe(document.body, { childList: true, subtree: true });
  });
  // Traduit aussi les boîtes de confirmation
  const nativeConfirm = window.confirm.bind(window);
  window.confirm = (msg) => nativeConfirm(translateText(String(msg)));
}

// Bouton FR / EN dans la barre du haut
document.addEventListener("DOMContentLoaded", () => {
  const bar = document.querySelector(".topbar");
  if (!bar) return;
  const btn = document.createElement("button");
  btn.className = "lang-switch";
  btn.title = LANG === "fr" ? "English" : "Français";
  btn.textContent = LANG === "fr" ? "🇬🇧 EN" : "🇫🇷 FR";
  btn.addEventListener("click", () => {
    try { localStorage.setItem("lang", LANG === "fr" ? "en" : "fr"); } catch { /* stockage indisponible */ }
    location.reload();
  });
  const spacer = bar.querySelector(".spacer");
  (spacer ? spacer.nextSibling : null) ? bar.insertBefore(btn, spacer.nextSibling) : bar.append(btn);
});
