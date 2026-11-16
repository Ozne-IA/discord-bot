# 🚂 Passer le bot sur Railway (24 h/24, sans ton PC)

Ce guide déménage le bot de ton PC vers Railway, en gardant ton domaine (`panel.clipmovestudio.app`) et toutes les données des serveurs.

Compte environ **45 minutes** la première fois. Le code est déjà prêt : tu n'as rien à modifier dans les fichiers.

> 🔒 Tout ce qui touche à tes comptes (mots de passe, paiement, tokens) se fait par toi. Ne colle jamais ton token ou tes clés dans un chat, une capture d'écran ou un fichier envoyé sur GitHub.

---

## Ce que ça coûte

Railway demande le forfait **Hobby** (environ 5 $ par mois, avec 5 $ d'utilisation inclus). Le bot seul rentre en général dedans. L'assistant IA est payé à part, sur ton compte Anthropic, comme maintenant.

---

## Vue d'ensemble

| # | Étape | Où | Le bot est… |
|---|---|---|---|
| 1 | Sauvegarder la base | Discord | sur ton PC |
| 2 | Envoyer le code sur GitHub (privé) | GitHub Desktop | sur ton PC |
| 3 | Créer le projet Railway | railway.com | sur ton PC |
| 4 | Ajouter le volume | Railway | sur ton PC |
| 5 | **Arrêter le PC**, puis coller les variables | PC + Railway | **sur Railway** |
| 6 | Brancher le domaine | Cloudflare + Railway | sur Railway |
| 7 | Remettre les données avec `/restore` | Discord | sur Railway |
| 8 | Vérifier | navigateur + Discord | sur Railway |

⚠️ **Le bot ne doit jamais tourner à deux endroits en même temps** (même token). Sinon chaque commande reçoit deux réponses et les données se mélangent. C'est pour ça que l'étape 5 commence par fermer `start.bat`.

---

## 1. Sauvegarder la base (sur ton PC)

1. Vérifie que le bot tourne encore sur ton PC.
2. Dans Discord, sur n'importe quel serveur où il est, tape **`/backup`**.
3. Le bot t'envoie un fichier `bot_AAAAMMJJ_HHMMSS.db` (visible par toi seul). Clique dessus et **télécharge-le**. Garde-le précieusement : il contient la configuration et les données de tous les serveurs.

Le fichier doit faire moins de 8 Mo pour passer par Discord. Si le bot répond « trop lourde pour Discord », le fichier est dans `discord-bot\data\backups\` sur ton PC : prends-le là.

---

## 2. Envoyer le code sur GitHub (dépôt privé)

Le dossier est déjà prêt (dépôt Git créé, fichiers ajoutés). Le fichier `.env` et la base de données **ne sont pas inclus** : ils sont ignorés exprès.

Le plus simple, sans ligne de commande :

1. Crée un compte sur <https://github.com> si tu n'en as pas, puis active la double authentification.
2. Installe **GitHub Desktop** : <https://desktop.github.com> et connecte-toi.
3. **File → Add local repository…** → choisis le dossier `Bot Discord - Panel web\discord-bot`.
4. GitHub Desktop affiche la liste des fichiers. Vérifie qu'il n'y a **ni `.env` ni `data`** dedans (ils sont exclus exprès).
5. En bas à gauche, dans **Summary**, écris `Version 14.1` → **Commit to main**.
6. Clique sur **Publish repository** :
   - Nom : par exemple `discord-bot`
   - ✅ **Laisse coché « Keep this code private »** (très important)
7. Valide. Le code est envoyé.

---

## 3. Créer le projet Railway

1. Va sur <https://railway.com> → **Login** → **Login with GitHub**.
2. Prends le forfait **Hobby** (Settings du compte → Plans). Railway te demandera ta carte : c'est toi qui la saisis.
3. **New Project** → **Deploy from GitHub repo** → autorise Railway à voir ton dépôt `discord-bot` → choisis-le.
4. Railway lit le `Dockerfile` et `railway.json` tout seul et lance une première construction (2 à 4 minutes).

Cette première tentative **va échouer** (« DISCORD_TOKEN manquant ») : c'est normal, les variables ne sont pas encore mises. Le bot sur ton PC continue de tourner pendant ce temps.

Conseil : dans le service → **Settings → Deploy → Region**, choisis **EU West (Amsterdam)**, plus proche de la France.

---

## 4. Ajouter le volume (sinon tout s'efface à chaque mise à jour)

1. Dans le projet, fais un **clic droit sur le service** (ou `Ctrl+K` → « Volume ») → **Attach Volume**.
2. Chemin de montage : **`/app/data`** (exactement).
3. Valide. La base de données, les logs et les sauvegardes iront dedans.

Tu n'as pas besoin de la variable `RAILWAY_RUN_UID` : le bot règle lui-même les droits du volume au démarrage.

---

## 5. Arrêter le PC, puis donner les variables à Railway

1. **Ferme le bot sur ton PC** : fenêtre `start.bat` → `Ctrl+C` (ou ferme-la), et ferme aussi la fenêtre « Tunnel Cloudflare ».
2. Sur Railway : service → onglet **Variables** → bouton **Raw Editor**.
3. Ouvre ton fichier `discord-bot\.env` dans le Bloc-notes, **copie tout**, colle-le dans le Raw Editor.
4. Dans le Raw Editor, **supprime ces lignes** :
   - `CLOUDFLARE_TUNNEL_TOKEN=…` (plus besoin du tunnel)
   - `DEV_GUILD_ID=…` (laisse les commandes globales)
   - `DATABASE_PATH=…` (le chemin par défaut va dans le volume)
5. Vérifie qu'il reste bien :

   | Variable | Valeur |
   |---|---|
   | `DISCORD_TOKEN` | ton token (déjà dans le .env) |
   | `DISCORD_CLIENT_SECRET` | ton client secret |
   | `PUBLIC_URL` | `https://panel.clipmovestudio.app` (sans `/` à la fin) |
   | `PORT` | `8080` |
   | `CONTACT` | ton contact |
   | `PREMIUM_SKU_ID`, `TWITCH_…`, `ANTHROPIC_…` | comme sur ton PC (vides si tu ne t'en sers pas) |

6. **Update Variables** puis **Deploy** (ou « Apply changes »). Railway reconstruit et démarre le bot.
7. Onglet **Deployments → View Logs** : tu dois voir `Connecté en tant que …`. Le bot est en ligne sur Railway 🎉

---

## 6. Brancher ton domaine sur Railway

Aujourd'hui, `panel.clipmovestudio.app` pointe vers le tunnel de ton PC. On le redirige vers Railway.

**Dans Cloudflare (enlever le tunnel)**

1. <https://one.dash.cloudflare.com> → **Networks → Tunnels** → ton tunnel → **Configure** → onglet **Public Hostname**.
2. Supprime la ligne `panel.clipmovestudio.app`. Cloudflare retire aussi l'ancien enregistrement DNS.

**Dans Railway (ajouter le domaine)**

3. Service → **Settings → Networking → Custom Domain** → tape `panel.clipmovestudio.app`, port **8080**.
4. Railway affiche un enregistrement **CNAME** (et parfois un **TXT** de vérification). Laisse la page ouverte.

**Dans Cloudflare (ajouter le nouvel enregistrement)**

5. <https://dash.cloudflare.com> → `clipmovestudio.app` → **DNS → Records → Add record** :
   - Type **CNAME**, nom **`panel`**, cible : celle donnée par Railway, proxy **orange (activé)**.
   - Si Railway a donné un **TXT**, ajoute-le aussi tel quel.
6. **SSL/TLS → Overview** : mode **Full** (pas « Flexible », sinon boucle de redirection).
7. Attends que Railway affiche une coche verte à côté du domaine (quelques minutes, parfois jusqu'à 1 h).

Rien à changer sur le portail Discord : l'adresse de redirection `https://panel.clipmovestudio.app/callback` reste la même.

---

## 7. Remettre les données

1. Dans Discord, tape **`/restore`** et joins le fichier `.db` téléchargé à l'étape 1.
2. Le bot vérifie le fichier, répond « Sauvegarde vérifiée », puis redémarre tout seul (environ 30 secondes).
3. L'ancienne base (vide) est gardée dans le volume, au cas où.

`/restore`, comme `/backup`, est réservé au propriétaire du bot (toi). Personne d'autre ne peut l'utiliser.

---

## 8. Vérifier

- [ ] `https://panel.clipmovestudio.app` affiche le site.
- [ ] `https://panel.clipmovestudio.app/status` indique **En ligne**.
- [ ] La connexion au panel avec Discord marche, et tes serveurs y sont avec leurs réglages.
- [ ] `/ping` répond une seule fois (si deux réponses : le bot tourne encore sur ton PC).
- [ ] `/rank` montre l'XP d'avant le déménagement.
- [ ] Coller le lien du site dans Discord montre l'aperçu avec l'image.

---

## Après : mettre à jour le bot

1. Modifie le code sur ton PC (ou demande-moi une nouvelle version).
2. Dans **GitHub Desktop** : écris un petit résumé en bas à gauche → **Commit to main** → **Push origin**.
3. Railway voit le changement, reconstruit et redémarre le bot tout seul (2 à 4 minutes). Les données restent dans le volume.

Ne relance **plus** `start.bat` avec le même token pendant que Railway tourne. Pour tester sans risque, crée une deuxième application Discord (bot de test) avec son propre token, et mets ce token-là dans le `.env` de ton PC.

**Sauvegardes** : fais un `/backup` de temps en temps (par exemple une fois par semaine) et garde le fichier chez toi.

---

## Problèmes fréquents

| Symptôme | Cause probable | Solution |
|---|---|---|
| Construction en échec sur Railway | Erreur dans le code poussé | **Deployments → View Logs**, envoie-moi les dernières lignes |
| `DISCORD_TOKEN manquant` dans les logs | Variables pas encore enregistrées | Étape 5 |
| Chaque commande répond deux fois | Le bot tourne aussi sur ton PC | Ferme `start.bat` |
| Données vides après une mise à jour | Pas de volume, ou mauvais chemin | Volume monté sur **`/app/data`** (étape 4), puis `/restore` |
| Le site ne s'ouvre pas | DNS pas encore propagé ou mauvais port | Port **8080** dans Railway, CNAME `panel` dans Cloudflare, attends un peu |
| « Too many redirects » | SSL Cloudflare en Flexible | SSL/TLS en **Full** |
| La connexion au panel échoue | `PUBLIC_URL` faux | `https://panel.clipmovestudio.app` sans `/` final, puis redéploie |
| `/restore` dit « version plus récente » | Le bot sur Railway est plus ancien que la sauvegarde | Pousse la dernière version sur GitHub, puis recommence |
| Healthcheck en échec | Le bot plante au démarrage | Lis les logs : la vraie erreur est juste au-dessus |

**Revenir sur ton PC en urgence** : fais d'abord un `/backup` pour emporter les données. Sur Railway, onglet **Deployments** → menu **⋮** du déploiement actif → **Remove**, puis relance `start.bat` et remets le Public Hostname du tunnel dans Cloudflare. Termine avec `/restore` sur ton PC.
