"""Modèles de configuration prêts à l'emploi (appliqués depuis le panel ou l'assistant de démarrage).

Un modèle ne contient aucun ID de salon ou de rôle : uniquement des textes et des réglages.
Il s'ajoute à la configuration existante (les salons et rôles déjà choisis sont conservés).
Les réglages 💎 qu'il contient (couleur, messages) ne s'appliquent qu'aux serveurs Premium.
"""
from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "gaming": {
        "name": "🎮 Gaming",
        "description": "Communauté de joueurs : niveaux, mini-jeux, économie, vocaux temporaires, alertes de stream.",
        "config": {
            "brand": {"color": "#9B59B6"},
            "welcome": {"message": "🎮 {mention} vient de rejoindre **{server}** ! Prépare ta manette, tu es le joueur n°{count} 🔥"},
            "verification": {"rules": [
                "Respect et fair-play avec tout le monde, en jeu comme sur Discord.",
                "Pas de triche, de hack ni de vente de comptes.",
                "Pas de spam, de pub ou de liens douteux.",
                "Les salons vocaux ne sont pas des salons de musique à fond.",
                "Les décisions du staff sont à respecter.",
            ]},
            "tickets": {"types": {
                "support": {"label": "Aide", "emoji": "🛠️", "description": "Un souci sur le serveur"},
                "report": {"label": "Signaler un joueur", "emoji": "🚨", "description": "Triche, insulte, comportement"},
                "team": {"label": "Rejoindre la team", "emoji": "🏆", "description": "Candidature pour l'équipe",
                         "questions": ["Ton pseudo en jeu", "Ton âge", "Tes jeux et ton niveau", "Pourquoi nous rejoindre ?"]},
                "partnership": {"label": "Partenariat", "emoji": "🤝", "description": "Proposer un partenariat"},
            }},
            "leveling": {"enabled": True, "xp_min": 15, "xp_max": 25, "voice_enabled": True,
                         "level_up_message": "⚡ GG {mention}, tu passes **niveau {level}** !"},
            "economy": {"enabled": True, "currency_name": "gemmes", "currency_emoji": "💎"},
            "games": {"enabled": True},
            "temp_voice": {"enabled": True, "name_template": "🎮 Squad de {name}"},
            "starboard": {"emoji": "🔥", "threshold": 4},
            "custom_commands": [{"trigger": "!regles", "response": "📜 Lis les règles dans le salon des règles avant de jouer avec nous !",
                                 "mode": "exact", "embed": True}],
        },
    },
    "community": {
        "name": "💬 Communauté",
        "description": "Serveur de discussion : accueil chaleureux, suggestions, anniversaires, niveaux.",
        "config": {
            "brand": {"color": "#3498DB"},
            "welcome": {"message": "👋 Bienvenue {mention} sur **{server}** ! Présente-toi et fais comme chez toi, tu es notre {count}e membre 💙"},
            "verification": {"rules": [
                "Sois bienveillant(e) : pas d'insulte, de harcèlement ni de discrimination.",
                "Pas de spam, de flood ni de publicité sans autorisation.",
                "Pas de contenu choquant, NSFW ou illégal.",
                "Utilise les bons salons et reste dans le sujet.",
                "Écoute le staff, il est là pour aider.",
            ]},
            "leveling": {"enabled": True},
            "birthdays": {"enabled": True},
            "suggestions": {"enabled": True},
            "starboard": {"emoji": "⭐", "threshold": 3},
            "economy": {"enabled": True},
            "games": {"enabled": True},
        },
    },
    "pro": {
        "name": "💼 Pro / École",
        "description": "Entreprise, association ou classe : sobre, sécurisé, tickets de support, pas de jeux.",
        "config": {
            "brand": {"color": "#2C3E50"},
            "welcome": {"message": "Bienvenue {mention} sur **{server}**. Merci de lire le règlement et de te vérifier pour accéder aux salons.",
                        "goodbye_message": "**{name}** a quitté le serveur."},
            "verification": {"captcha": True, "rules": [
                "Restez courtois et professionnels.",
                "Les informations partagées ici restent confidentielles.",
                "Utilisez les salons prévus pour chaque sujet.",
                "Pour toute demande, ouvrez un ticket plutôt qu'un message privé.",
            ]},
            "tickets": {"types": {
                "support": {"label": "Support", "emoji": "🛠️", "description": "Question ou problème technique",
                            "questions": ["Sujet de la demande", "Description détaillée", "Urgence (faible / moyenne / haute)"]},
                "admin": {"label": "Administratif", "emoji": "📄", "description": "Documents, inscriptions, factures"},
                "other": {"label": "Autre", "emoji": "💬", "description": "Autre demande"},
            }},
            "leveling": {"enabled": False},
            "economy": {"enabled": False},
            "games": {"enabled": False},
            "automod": {"block_invites": True, "max_mentions": 3},
            "anti_raid": {"min_account_age_days": 14},
            "starboard": {"enabled": False},
        },
    },
    "streamer": {
        "name": "📺 Streamer / Créateur",
        "description": "Communauté d'un créateur : alertes de live et de vidéos, rôles de notification, giveaways.",
        "config": {
            "brand": {"color": "#E91E63"},
            "welcome": {"message": "🎉 {mention} rejoint la commu de **{server}** ! Active les notifs pour ne rater aucun live 🔴"},
            "roles": {},
            "leveling": {"enabled": True, "voice_enabled": True},
            "economy": {"enabled": True, "currency_name": "points", "currency_emoji": "⭐"},
            "games": {"enabled": True},
            "suggestions": {"enabled": True},
            "custom_commands": [
                {"trigger": "!live", "response": "🔴 Les lives sont annoncés automatiquement dans le salon des annonces !", "mode": "exact", "embed": True},
                {"trigger": "!reseaux", "response": "📱 Retrouve tous mes réseaux dans le salon des liens.", "mode": "exact", "embed": True},
            ],
        },
    },
}


def template_list() -> list[dict]:
    return [{"id": key, "name": t["name"], "description": t["description"]} for key, t in TEMPLATES.items()]
