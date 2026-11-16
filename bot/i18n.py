"""Langues du bot (français par défaut, anglais).

1. Les descriptions des commandes slash sont traduites automatiquement pour les membres
   dont Discord est en anglais (Translator de discord.py).
2. `tr(guild, texte)` traduit les textes par défaut (panneaux, messages automatiques) selon la langue
   choisie pour le serveur dans le panel (Général → Langue du bot).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    pass

I18N_VERSION = "7"  # à incrémenter quand on modifie les traductions des commandes (renvoi à Discord)

COMMANDS_EN = {
    # --- v13
    "Événements avec inscription et rappel": "Events with sign-up and reminder",
    "Crée un événement (date et heure du serveur)": "Create an event (server date and time)",
    "Nom de l'événement": "Event name", "Ex : 25/12 ou 25/12/2026": "E.g. 25/12 or 25/12/2026 (day/month)",
    "Ex : 20h30 ou 20:30": "E.g. 20:30", "Détails (facultatif)": "Details (optional)",
    "Nombre de places (0 = illimité)": "Number of spots (0 = unlimited)", "Salon où publier (vide = ici)": "Channel to post in (empty = here)",
    "Les événements à venir": "Upcoming events", "Annule un événement (les inscrits sont prévenus)": "Cancel an event",
    "Tournois à élimination directe": "Single-elimination tournaments",
    "Crée un tournoi avec inscriptions par bouton": "Create a tournament with button sign-ups", "Nom du tournoi": "Tournament name",
    "Joueurs maximum (16 en gratuit, 💎 64)": "Maximum players (16 free, 💎 64)",
    "Argent du serveur pour le champion (0 = rien)": "Server money for the champion (0 = nothing)", "Salon (vide = ici)": "Channel (empty = here)",
    "Ferme les inscriptions et tire le tableau au sort": "Close sign-ups and draw the bracket",
    "Indique le gagnant d'un match en cours": "Set the winner of a current match", "Affiche le tableau d'un tournoi": "Show a tournament bracket",
    "Annule un tournoi": "Cancel a tournament",
    "Pose une question sur le serveur à l'assistant IA": "Ask the AI assistant a question about the server",
    "Résumé IA du ticket actuel (visible par toi seul)": "AI summary of the current ticket (only visible to you)",
    "L'IA rédige une annonce, tu la relis puis tu la publies": "The AI drafts an announcement, you review and post it",
    "De quoi parle l'annonce (dates, infos importantes…)": "What the announcement is about (dates, key info…)",
    "Style de l'annonce": "Announcement style", "Enthousiaste": "Enthusiastic", "Sérieux": "Serious", "Drôle": "Funny",
    "Signalements en attente de traitement": "Reports waiting to be handled", "Signaler le message": "Report message",
    # --- v12
    "Ton profil : niveau, argent, séries, badges (ou celui d'un membre)": "Your profile: level, money, streaks, badges (or a member's)",
    "Liste des succès : débloqués et à débloquer": "Achievements: unlocked and still to unlock",
    "Tes quêtes du jour (et de la semaine 💎) avec ta progression": "Your daily quests (and weekly 💎) with your progress",
    "Activité du staff : sanctions, tickets pris en charge, notes": "Staff activity: punishments, claimed tickets, notes",
    "Période analysée": "Period", "7 derniers jours": "Last 7 days", "30 derniers jours": "Last 30 days",
    "90 derniers jours": "Last 90 days", "Depuis le début": "All time",
    "Supprime une note interne (par son numéro)": "Delete a staff note (by its number)",
    "Ta banque : l'argent rapporte des intérêts chaque jour": "Your bank: money earns interest every day",
    "Ton argent à la banque et le taux d'intérêt": "Your bank balance and interest rate",
    "Mets de l'argent à la banque (nombre ou « tout »)": "Deposit money in the bank (amount or \"all\")",
    "Reprends de l'argent de la banque (nombre ou « tout »)": "Withdraw money from the bank (amount or \"all\")",
    "Prévisualise le message de bienvenue": "Preview the welcome message",
    "Envoie le panneau règles + vérification ici": "Post the rules + verification panel here",
    "Envoie le panneau des rôles de notification ici": "Post the notification roles panel here",
    "Envoie le panneau de tickets ici": "Post the ticket panel here",
    "Gestion des tickets": "Ticket management",
    "Ajoute un membre au ticket": "Add a member to the ticket",
    "Retire un membre du ticket": "Remove a member from the ticket",
    "Change la priorité du ticket": "Change the ticket priority",
    "🟢 basse": "🟢 low", "🟡 normale": "🟡 normal", "🟠 haute": "🟠 high", "🔴 urgente": "🔴 urgent",
    "Ferme le ticket actuel": "Close the current ticket",
    "Statistiques des tickets": "Ticket statistics",
    "Affiche ton niveau (ou celui d'un membre)": "Show your level (or a member's)",
    "Classement des membres les plus actifs": "Leaderboard of the most active members",
    "Depuis toujours, cette semaine ou ce mois (💎 Premium pour semaine/mois)": "All time, this week or this month (💎 Premium for week/month)",
    "Depuis toujours": "All time", "💎 Cette semaine": "💎 This week", "💎 Ce mois": "💎 This month",
    "Gestion de l'XP (staff)": "XP management (staff)",
    "Ajoute de l'XP à un membre": "Give XP to a member",
    "Retire de l'XP à un membre": "Remove XP from a member",
    "Remet l'XP d'un membre à zéro": "Reset a member's XP",
    "Avertit un membre": "Warn a member",
    "Annule un avertissement (par numéro de cas)": "Cancel a warning (by case number)",
    "Casier d'un membre (sanctions + notes)": "A member's record (punishments + notes)",
    "Ajoute une note interne (invisible pour le membre)": "Add an internal note (hidden from the member)",
    "Rend un membre muet temporairement (timeout)": "Temporarily mute a member (timeout)",
    "Ex : 10m, 1h, 2h30m, 7d (max 28d)": "e.g. 10m, 1h, 2h30m, 7d (max 28d)",
    "Retire le mute d'un membre": "Unmute a member",
    "Expulse un membre": "Kick a member",
    "Bannit un membre (définitivement ou temporairement)": "Ban a member (permanently or temporarily)",
    "Laisse vide pour un ban définitif. Ex : 1d, 7d, 30d": "Leave empty for a permanent ban. e.g. 1d, 7d, 30d",
    "Supprimer ses messages des X derniers jours (0-7)": "Delete their messages from the last X days (0-7)",
    "Ban + déban immédiat pour effacer les messages récents": "Ban + immediate unban to wipe recent messages",
    "Débannit un utilisateur par son ID": "Unban a user by ID",
    "Supprime des messages (avec filtres optionnels)": "Delete messages (with optional filters)",
    "Nombre de messages à analyser (1-100)": "Number of messages to scan (1-100)",
    "Uniquement ce membre": "Only this member", "Uniquement les bots": "Only bots",
    "Uniquement les messages contenant ce texte": "Only messages containing this text",
    "Définit le mode lent du salon (0 pour désactiver)": "Set the channel slowmode (0 to disable)",
    "Verrouille le salon (plus personne ne peut écrire)": "Lock the channel (nobody can write)",
    "Déverrouille le salon": "Unlock the channel",
    "Nombre de sanctions par modérateur": "Punishments per moderator",
    "Active/désactive le lockdown anti-raid (refuse les arrivées)": "Turn the anti-raid lockdown on/off (refuses joins)",
    "Ajoute/retire un utilisateur de la whitelist sécurité": "Add/remove a user from the security whitelist",
    "État des protections du serveur": "Server protection status",
    "Liste de toutes les commandes": "List of all commands",
    "Lien du panel web pour configurer le bot": "Link to the web dashboard to configure the bot",
    "Lien pour ajouter le bot sur un autre serveur": "Link to add the bot to another server",
    "Latence du bot": "Bot latency", "Informations sur le bot": "Bot information",
    "Informations sur le serveur": "Server information", "Informations sur un membre": "Member information",
    "Vérifie que les salons, rôles et permissions sont OK": "Check that channels, roles and permissions are OK",
    "[Propriétaire du bot] Sauvegarde de la base de données": "[Bot owner] Database backup",
    "[Propriétaire du bot] Resynchronise les commandes slash": "[Bot owner] Resync slash commands",
    "[Propriétaire du bot] Remplace la base par une sauvegarde": "[Bot owner] Replace the database with a backup",
    "Fichier .db ou .db.gz obtenu avec /backup ou la sauvegarde automatique": ".db or .db.gz file from /backup or the automatic backup",
    "Statut Premium de ce serveur et avantages": "This server's Premium status and perks",
    "[Propriétaire du bot] Gérer les accès Premium": "[Bot owner] Manage Premium access",
    "Offre Premium à un serveur": "Gift Premium to a server",
    "ID du serveur (vide = ce serveur)": "Server ID (empty = this server)",
    "Durée en jours (vide = à vie)": "Duration in days (empty = lifetime)",
    "Retire le Premium offert à un serveur": "Remove gifted Premium from a server",
    "Liste des serveurs Premium": "List of Premium servers",
    "Envoie une réponse enregistrée dans le ticket": "Send a saved reply in the ticket",
    "Nom de la réponse (réglées dans le panel → Tickets)": "Reply name (set in the dashboard → Tickets)",
    "Voir ou effacer les données que le bot garde sur toi": "See or delete the data the bot keeps about you",
    "Reçois un fichier avec toutes les données que le bot garde sur toi": "Get a file with all the data the bot keeps about you",
    "Efface tes niveaux, ton argent, tes succès, rappels et anniversaire": "Delete your levels, money, achievements, reminders and birthday",
    "Voter pour le bot sur top.gg et récupérer ta récompense": "Vote for the bot on top.gg and claim your reward",
    "💎 Giveaways (Premium)": "💎 Giveaways (Premium)", "Lance un giveaway": "Start a giveaway", "Ce qu'on gagne": "The prize",
    "Ex : 30m, 2h, 1d, 7d": "e.g. 30m, 2h, 1d, 7d", "Nombre de gagnants": "Number of winners",
    "Salon du giveaway (par défaut : ici)": "Giveaway channel (default: here)",
    "Rôle nécessaire pour participer": "Role required to enter",
    "Termine un giveaway maintenant": "End a giveaway now", "Tire de nouveaux gagnants": "Draw new winners",
    "Giveaways en cours": "Running giveaways",
    "💎 Sondages (Premium)": "💎 Polls (Premium)", "Crée un sondage à boutons": "Create a button poll", "La question": "The question",
    "Les choix séparés par | (2 à 10). Ex : Oui | Non | Peut-être": "Options separated by | (2 to 10). e.g. Yes | No | Maybe",
    "Fin automatique (ex : 1h, 1d). Vide = pas de fin": "Automatic end (e.g. 1h, 1d). Empty = no end",
    "Termine un sondage et affiche le résultat final": "End a poll and show the final result",
    "Ton solde (ou celui d'un membre)": "Your balance (or a member's)",
    "Récupère ta récompense quotidienne (bonus si tu reviens chaque jour)": "Claim your daily reward (bonus if you come back every day)",
    "Travaille pour gagner de l'argent": "Work to earn money", "Donne de l'argent à un membre": "Give money to a member",
    "Classement des membres les plus riches": "Leaderboard of the richest members",
    "Gestion de l'économie (staff)": "Economy management (staff)",
    "Ajoute de l'argent à un membre": "Give money to a member (staff)", "Retire de l'argent à un membre": "Take money from a member",
    "Remet à zéro l'argent et l'inventaire d'un membre": "Reset a member's money and inventory",
    "💎 Boutique du serveur": "💎 Server shop", "💎 Achète un objet de la boutique": "💎 Buy an item from the shop",
    "💎 Ton inventaire (ou celui d'un membre)": "💎 Your inventory (or a member's)",
    "Rappels personnels": "Personal reminders", "Programme un rappel (ex : 10m, 2h, 1d)": "Schedule a reminder (e.g. 10m, 2h, 1d)",
    "Dans combien de temps (ex : 10m, 1h30m, 2d)": "In how long (e.g. 10m, 1h30m, 2d)", "De quoi te rappeler": "What to remind you about",
    "Si tes messages privés sont fermés, te le rappeler dans ce salon": "If your DMs are closed, remind you in this channel",
    "Tes rappels en attente": "Your pending reminders", "Supprime un de tes rappels": "Delete one of your reminders",
    "Parie sur pile ou face (×2 si tu gagnes)": "Bet on heads or tails (×2 if you win)", "🪙 Pile": "🪙 Tails", "👑 Face": "👑 Heads",
    "Lance les dés contre le bot (le plus grand total gagne ×2)": "Roll dice against the bot (highest total wins ×2)",
    "Devine le nombre entre 1 et 100 en 7 essais": "Guess the number between 1 and 100 in 7 tries",
    "Question de culture générale : le premier qui trouve gagne": "Trivia question: the first to answer right wins",
    "💎 Roulette : rouge/noir/pair/impair (×2) ou un numéro (×36)": "💎 Roulette: red/black/even/odd (×2) or a number (×36)",
    "rouge, noir, pair, impair ou un numéro de 0 à 36": "red, black, even, odd or a number from 0 to 36",
    "💎 Blackjack contre le croupier": "💎 Blackjack against the dealer",
    "Propose une idée pour le serveur": "Suggest an idea for the server",
    "Suivi des invitations": "Invite tracking", "Invitations d'un membre (ou les tiennes)": "A member's invites (or yours)",
    "Les membres qui ont invité le plus de monde": "Members who invited the most people",
    "Gère ton salon vocal temporaire": "Manage your temporary voice channel", "Renomme ton salon vocal": "Rename your voice channel",
    "Nombre maximum de personnes (0 = illimité)": "Maximum number of users (0 = unlimited)",
    "Plus personne ne peut rejoindre (sauf invités)": "Nobody can join anymore (except invited users)",
    "Tout le monde peut de nouveau rejoindre": "Everyone can join again",
    "Autorise un membre à rejoindre même si c'est verrouillé": "Allow a member to join even when locked",
    "Donne la propriété du salon à un autre membre": "Give channel ownership to another member",
    "Anniversaires du serveur": "Server birthdays", "Enregistre ta date d'anniversaire": "Save your birthday",
    "Supprime ta date d'anniversaire": "Delete your birthday", "Les prochains anniversaires du serveur": "Upcoming birthdays on the server",
}

ENGLISH_LOCALES = {discord.Locale.american_english, discord.Locale.british_english}


class BotTranslator(app_commands.Translator):
    async def translate(self, string: app_commands.locale_str, locale: discord.Locale,
                        context: app_commands.TranslationContext) -> str | None:
        if locale in ENGLISH_LOCALES:
            # Les noms de commandes restent identiques (on ne traduit que les descriptions et les choix)
            if context.location in (app_commands.TranslationContextLocation.command_name,
                                    app_commands.TranslationContextLocation.group_name,
                                    app_commands.TranslationContextLocation.parameter_name):
                return None
            return COMMANDS_EN.get(string.message)
        return None


# --------------------------------------------------------------------------- #
#  Textes par défaut selon la langue du serveur
# --------------------------------------------------------------------------- #
TEXTS_EN = {
    # panneaux
    "📜 Règles de {server}": "📜 Rules of {server}",
    "Respecte tout le monde.": "Respect everyone.",
    "Clique sur le bouton ci-dessous pour accepter les règles et accéder au serveur.":
        "Click the button below to accept the rules and access the server.",
    "J'accepte les règles": "I accept the rules",
    "🔔 Rôles de notification": "🔔 Notification roles",
    "Sélectionne dans le menu les sujets pour lesquels tu veux être mentionné(e).\n"
    "Désélectionne un sujet pour ne plus recevoir ses notifications.":
        "Pick the topics you want to be pinged for in the menu.\nUnselect a topic to stop its notifications.",
    "🔔 Choisis tes notifications…": "🔔 Choose your notifications…",
    "📩 Besoin d'aide ?": "📩 Need help?",
    "Choisis le type de demande dans le menu ci-dessous. Un salon privé sera créé avec le staff.":
        "Choose the type of request in the menu below. A private channel will be created with the staff.",
    "📩 Choisis le type de ticket…": "📩 Choose the ticket type…",
    # accueil / niveaux / anniversaires
    "👋 Nouveau membre !": "👋 New member!", "Compte créé": "Account created", "Membre n°": "Member #",
    "🎂 Joyeux anniversaire !": "🎂 Happy birthday!",
    # vérification
    "Tu as maintenant accès à tout le serveur. Amuse-toi bien !": "You now have access to the whole server. Have fun!",
    "✅ Vérifié(e)": "✅ Verified", "Tu es déjà vérifié(e) 👍": "You're already verified 👍",
    "🔐 Vérification anti-robot": "🔐 Anti-bot verification",
}

# Messages par défaut (defaults.json) et leur version anglaise : utilisés si l'admin ne les a pas modifiés
DEFAULT_MESSAGES_EN = {
    "Bienvenue {mention} sur **{server}** ! Tu es notre {count}e membre 🎉":
        "Welcome {mention} to **{server}**! You are member #{count} 🎉",
    "Salut {name} ! Bienvenue sur **{server}**. Pense à lire les règles et à te vérifier pour accéder au serveur.":
        "Hi {name}! Welcome to **{server}**. Remember to read the rules and verify yourself to access the server.",
    "**{name}** a quitté le serveur. Nous sommes maintenant {count}.":
        "**{name}** left the server. We are now {count}.",
    "🎉 {mention} passe au **niveau {level}** !": "🎉 {mention} reached **level {level}**!",
    "🎂 Joyeux anniversaire {mention} ! Toute l'équipe de **{server}** te souhaite une super journée 🎉":
        "🎂 Happy birthday {mention}! The whole **{server}** team wishes you a great day 🎉",
    "🔊 Salon de {name}": "🔊 {name}'s channel",
}


def language(guild: discord.Guild | int | None) -> str:
    from bot.config import gconf
    return gconf(guild).get("general", "language", default="fr") or "fr"


def tr(guild: discord.Guild | int | None, text: str, **values: str) -> str:
    """Traduit un texte par défaut selon la langue du serveur, puis remplace {variables}."""
    if language(guild) == "en":
        text = TEXTS_EN.get(text) or DEFAULT_MESSAGES_EN.get(text) or text
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
