"""Économie : monnaie du serveur.
Gratuit : /balance, /daily (avec série), /work, /pay, /richest, gestion staff (/eco).
💎 Premium : boutique configurable dans le panel (/shop, /buy), inventaire, nom et emoji de la monnaie."""
from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.i18n import language
from bot.pagination import Paginator, chunk
from bot.premium import require
from bot.utils import format_duration, reply_error

DAY = 86400
MAX_STREAK = 30
JOBS = [
    "Tu as livré des pizzas", "Tu as modéré un serveur Discord", "Tu as réparé un ordinateur",
    "Tu as donné un cours de maths", "Tu as streamé pendant 3 heures", "Tu as promené des chiens",
    "Tu as codé un site web", "Tu as monté une vidéo", "Tu as servi des cafés", "Tu as gagné un tournoi",
]


def money(guild: discord.Guild | int | None, amount: int) -> str:
    cfg = gconf(guild)
    emoji = cfg.get("economy", "currency_emoji", default="🪙") or ""
    name = cfg.get("economy", "currency_name", default="pièces") or ""
    if name == "pièces" and language(guild) == "en":
        name = "coins"
    return f"**{amount:,}** {emoji} {name}".replace(",", " ").strip()


def daily_reward(cfg_amount: int, bonus: int, streak: int) -> int:
    return cfg_amount + bonus * (min(streak, MAX_STREAK) - 1)


def next_streak(last_daily: float, streak: int, now: float) -> int:
    """Série conservée si le dernier /daily date de moins de 48 h, sinon on repart à 1."""
    return streak + 1 if now - last_daily < 2 * DAY else 1


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    # --- accès aux soldes ------------------------------------------------
    async def account(self, guild_id: int, user_id: int) -> dict:
        row = await self.db.fetchone("SELECT * FROM economy WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        if row:
            return dict(row)
        await self.db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?,?)", (guild_id, user_id))
        return {"guild_id": guild_id, "user_id": user_id, "balance": 0, "last_daily": 0, "streak": 0, "last_work": 0,
                "bank": 0}

    async def add(self, guild_id: int, user_id: int, amount: int) -> int:
        await self.account(guild_id, user_id)
        await self.db.execute("UPDATE economy SET balance = MAX(0, balance + ?) WHERE guild_id=? AND user_id=?",
                              (amount, guild_id, user_id))
        return (await self.account(guild_id, user_id))["balance"]

    async def spend(self, guild_id: int, user_id: int, amount: int) -> bool:
        """Retire `amount` seulement si le solde suffit (en une seule requête, sans risque de solde négatif)."""
        await self.account(guild_id, user_id)
        before = self.db.conn.total_changes
        await self.db.execute("UPDATE economy SET balance = balance - ? WHERE guild_id=? AND user_id=? AND balance >= ?",
                              (amount, guild_id, user_id, amount))
        return self.db.conn.total_changes > before

    async def _enabled(self, interaction: discord.Interaction) -> bool:
        if gconf(interaction.guild).get("economy", "enabled", default=True):
            return True
        await reply_error(interaction, "L'économie est désactivée sur ce serveur.")
        return False

    # --- gratuit ---------------------------------------------------------
    @app_commands.command(name="balance", description="Ton solde (ou celui d'un membre)")
    @app_commands.guild_only()
    async def balance(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        if not await self._enabled(interaction):
            return
        member = membre or interaction.user
        acc = await self.account(interaction.guild_id or 0, member.id)
        pos = await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM economy WHERE guild_id=? AND balance > ?",
                                     (interaction.guild_id, acc["balance"]))
        embed = embeds.base(f"💰 {member.display_name}", f"Solde : {money(interaction.guild, acc['balance'])}",
                            guild=interaction.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        if acc.get("bank"):
            embed.add_field(name="🏦 Banque", value=money(interaction.guild, acc["bank"]))
        embed.add_field(name="Classement", value=f"#{pos['p']}")
        embed.add_field(name="Série /daily", value=f"🔥 {acc['streak']} jour(s)")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne (bonus si tu reviens chaque jour)")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        if not await self._enabled(interaction):
            return
        cfg = gconf(interaction.guild)
        acc = await self.account(interaction.guild_id or 0, interaction.user.id)
        now = time.time()
        wait = acc["last_daily"] + DAY - now
        if wait > 0:
            await reply_error(interaction, f"Tu as déjà récupéré ta récompense. Reviens dans **{format_duration_s(wait)}**.")
            return
        streak = next_streak(acc["last_daily"], acc["streak"], now)
        gain = daily_reward(int(cfg.get("economy", "daily_amount", default=100)),
                            int(cfg.get("economy", "daily_streak_bonus", default=10)), streak)
        await self.db.execute("UPDATE economy SET balance = balance + ?, last_daily=?, streak=? WHERE guild_id=? AND user_id=?",
                              (gain, now, streak, interaction.guild_id, interaction.user.id))
        text = f"Tu reçois {money(interaction.guild, gain)} !\n🔥 Série : **{streak}** jour(s)"
        if streak > 1:
            text += " (bonus de série inclus)"
        await interaction.response.send_message(embed=embeds.success(text, "🎁 Récompense quotidienne"))
        self.bot.dispatch("activity", interaction.guild, interaction.user, interaction.channel, "daily", 1)

    @app_commands.command(name="work", description="Travaille pour gagner de l'argent")
    @app_commands.guild_only()
    async def work(self, interaction: discord.Interaction) -> None:
        if not await self._enabled(interaction):
            return
        cfg = gconf(interaction.guild)
        acc = await self.account(interaction.guild_id or 0, interaction.user.id)
        cooldown = int(cfg.get("economy", "work_cooldown_minutes", default=60)) * 60
        wait = acc["last_work"] + cooldown - time.time()
        if wait > 0:
            await reply_error(interaction, f"Tu es fatigué(e) 😴 Reviens dans **{format_duration_s(wait)}**.")
            return
        low = int(cfg.get("economy", "work_min", default=20))
        high = max(low, int(cfg.get("economy", "work_max", default=80)))
        gain = random.randint(low, high)
        await self.db.execute("UPDATE economy SET balance = balance + ?, last_work=? WHERE guild_id=? AND user_id=?",
                              (gain, time.time(), interaction.guild_id, interaction.user.id))
        await interaction.response.send_message(
            embed=embeds.success(f"{random.choice(JOBS)} et tu gagnes {money(interaction.guild, gain)}.", "💼 Travail"))
        self.bot.dispatch("activity", interaction.guild, interaction.user, interaction.channel, "work", 1)

    @app_commands.command(name="pay", description="Donne de l'argent à un membre")
    @app_commands.guild_only()
    async def pay(self, interaction: discord.Interaction, membre: discord.Member,
                  montant: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        if not await self._enabled(interaction):
            return
        if membre.bot or membre.id == interaction.user.id:
            await reply_error(interaction, "Choisis un autre membre (pas toi, pas un bot).")
            return
        if not await self.spend(interaction.guild_id or 0, interaction.user.id, montant):
            await reply_error(interaction, "Tu n'as pas assez d'argent.")
            return
        await self.add(interaction.guild_id or 0, membre.id, montant)
        await interaction.response.send_message(embed=embeds.success(
            f"{interaction.user.mention} a donné {money(interaction.guild, montant)} à {membre.mention}.", "💸 Virement"))

    @app_commands.command(name="richest", description="Classement des membres les plus riches")
    @app_commands.guild_only()
    async def richest(self, interaction: discord.Interaction) -> None:
        if not await self._enabled(interaction):
            return
        rows = await self.db.fetchall(
            "SELECT user_id, balance + bank AS balance FROM economy WHERE guild_id=? AND balance + bank > 0 "
            "ORDER BY balance + bank DESC LIMIT 100", (interaction.guild_id,))
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        pages = []
        for p, group in enumerate(chunk(rows, 10)):
            lines = [f"{medals.get(p * 10 + i, f'`#{p * 10 + i}`')} <@{r['user_id']}> — {money(interaction.guild, r['balance'])}"
                     for i, r in enumerate(group, 1)]
            pages.append(embeds.base("💰 Les plus riches", "\n".join(lines) or "Personne n'a encore d'argent.",
                                     guild=interaction.guild))
        await Paginator.send(interaction, pages)

    # --- banque -----------------------------------------------------------
    bank = app_commands.Group(name="banque", description="Ta banque : l'argent rapporte des intérêts chaque jour",
                              guild_only=True)

    async def _bank_ready(self, interaction: discord.Interaction) -> bool:
        if not await self._enabled(interaction):
            return False
        if not gconf(interaction.guild).get("economy", "bank_enabled", default=True):
            await reply_error(interaction, "La banque est désactivée sur ce serveur.")
            return False
        return True

    @bank.command(name="voir", description="Ton argent à la banque et le taux d'intérêt")
    async def bank_show(self, interaction: discord.Interaction) -> None:
        if not await self._bank_ready(interaction):
            return
        cfg = gconf(interaction.guild)
        acc = await self.account(interaction.guild_id or 0, interaction.user.id)
        rate = bank_rate(cfg.get("economy", "bank_interest", default=1.0))
        cap = int(cfg.get("economy", "bank_max", default=0) or 0)
        embed = embeds.base("🏦 Banque", guild=interaction.guild)
        embed.add_field(name="Porte-monnaie", value=money(interaction.guild, acc["balance"]))
        embed.add_field(name="Banque", value=money(interaction.guild, acc["bank"]))
        embed.add_field(name="Intérêts", value=f"{rate:g} % par jour" + (f" (jusqu'à {cap:,})".replace(",", " ") if cap else ""))
        embed.set_footer(text="/banque deposer et /banque retirer · « tout » accepté")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bank.command(name="deposer", description="Mets de l'argent à la banque (nombre ou « tout »)")
    async def bank_deposit(self, interaction: discord.Interaction, montant: str) -> None:
        if not await self._bank_ready(interaction):
            return
        gid, uid = interaction.guild_id or 0, interaction.user.id
        acc = await self.account(gid, uid)
        cap = int(gconf(interaction.guild).get("economy", "bank_max", default=0) or 0)
        amount = parse_amount(montant, acc["balance"])
        if cap:
            amount = min(amount or 0, max(0, cap - acc["bank"])) if amount is not None else None
        if not amount:
            await reply_error(interaction, "Montant invalide (ou banque pleine). Exemple : `/banque deposer 500` ou `tout`.")
            return
        if not await self.spend(gid, uid, amount):
            await reply_error(interaction, "Tu n'as pas assez d'argent dans ton porte-monnaie.")
            return
        await self.db.execute("UPDATE economy SET bank = bank + ? WHERE guild_id=? AND user_id=?", (amount, gid, uid))
        await interaction.response.send_message(embed=embeds.success(
            f"Tu as déposé {money(interaction.guild, amount)} à la banque.", "🏦 Dépôt"), ephemeral=True)

    @bank.command(name="retirer", description="Reprends de l'argent de la banque (nombre ou « tout »)")
    async def bank_withdraw(self, interaction: discord.Interaction, montant: str) -> None:
        if not await self._bank_ready(interaction):
            return
        gid, uid = interaction.guild_id or 0, interaction.user.id
        acc = await self.account(gid, uid)
        amount = parse_amount(montant, acc["bank"])
        if not amount:
            await reply_error(interaction, "Montant invalide. Exemple : `/banque retirer 500` ou `tout`.")
            return
        before = self.db.conn.total_changes
        await self.db.execute("UPDATE economy SET bank = bank - ?, balance = balance + ? "
                              "WHERE guild_id=? AND user_id=? AND bank >= ?", (amount, amount, gid, uid, amount))
        if self.db.conn.total_changes == before:
            await reply_error(interaction, "Tu n'as pas autant d'argent à la banque.")
            return
        await interaction.response.send_message(embed=embeds.success(
            f"Tu as retiré {money(interaction.guild, amount)} de la banque.", "🏦 Retrait"), ephemeral=True)

    @tasks.loop(hours=1)
    async def interest(self) -> None:
        """Une fois par jour (UTC) : intérêts versés sur l'argent placé à la banque."""
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if await self.db.get_setting(0, "bank_interest_day") == today:
            return
        await self.db.set_setting(0, "bank_interest_day", today)
        for guild in self.bot.guilds:
            cfg = gconf(guild)
            if not (cfg.get("economy", "enabled", default=True) and cfg.get("economy", "bank_enabled", default=True)):
                continue
            rate = bank_rate(cfg.get("economy", "bank_interest", default=1.0))
            cap = int(cfg.get("economy", "bank_max", default=0) or 0) or 10**15
            if rate > 0:
                await self.db.execute(
                    "UPDATE economy SET bank = MIN(?, bank + CAST(bank * ? / 100 AS INTEGER)) "
                    "WHERE guild_id=? AND bank > 0 AND bank < ?", (cap, rate, guild.id, cap))

    @interest.before_loop
    async def _before_interest(self) -> None:
        await self.bot.wait_until_ready()

    async def cog_load(self) -> None:
        self.interest.start()

    async def cog_unload(self) -> None:
        self.interest.cancel()

    eco = app_commands.Group(name="eco",description="Gestion de l'économie (staff)", guild_only=True,
                             default_permissions=discord.Permissions(manage_guild=True))

    @eco.command(name="give", description="Ajoute de l'argent à un membre")
    async def eco_give(self, interaction: discord.Interaction, membre: discord.Member,
                       montant: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        total = await self.add(interaction.guild_id or 0, membre.id, montant)
        await interaction.response.send_message(embed=embeds.success(
            f"+{money(interaction.guild, montant)} pour {membre.mention} (solde : {money(interaction.guild, total)})."),
            ephemeral=True)

    @eco.command(name="take", description="Retire de l'argent à un membre")
    async def eco_take(self, interaction: discord.Interaction, membre: discord.Member,
                       montant: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        total = await self.add(interaction.guild_id or 0, membre.id, -montant)
        await interaction.response.send_message(embed=embeds.success(
            f"-{money(interaction.guild, montant)} pour {membre.mention} (solde : {money(interaction.guild, total)})."),
            ephemeral=True)

    @eco.command(name="reset", description="Remet à zéro l'argent et l'inventaire d'un membre")
    async def eco_reset(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        await self.db.execute("DELETE FROM economy WHERE guild_id=? AND user_id=?", (interaction.guild_id, membre.id))
        await self.db.execute("DELETE FROM inventory WHERE guild_id=? AND user_id=?", (interaction.guild_id, membre.id))
        await interaction.response.send_message(embed=embeds.success(f"Économie de {membre.mention} remise à zéro."),
                                                ephemeral=True)

    # --- 💎 boutique -------------------------------------------------------
    @staticmethod
    def shop_items(guild: discord.Guild | None) -> list[dict]:
        return list(gconf(guild).get("economy", "shop", default=[]) or [])

    @app_commands.command(name="shop", description="💎 Boutique du serveur")
    @app_commands.guild_only()
    async def shop(self, interaction: discord.Interaction) -> None:
        if not await self._enabled(interaction) or not await require(interaction, "La boutique"):
            return
        items = self.shop_items(interaction.guild)
        if not items:
            await reply_error(interaction, "La boutique est vide. Les admins peuvent la remplir sur le panel (onglet Économie).")
            return
        pages = []
        for group in chunk(items, 8):
            embed = embeds.base("🛒 Boutique", "Achète avec `/buy <objet>`.", guild=interaction.guild)
            for it in group:
                extra = f"\nDonne le rôle <@&{it['role']}>" if it.get("role") else ""
                embed.add_field(name=f"{it['name']} — {money(interaction.guild, int(it['price']))}",
                                value=(it.get("description") or "—") + extra, inline=False)
            pages.append(embed)
        await Paginator.send(interaction, pages)

    async def _item_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=f"{it['name']} ({it['price']})"[:100], value=it["name"][:100])
                for it in self.shop_items(interaction.guild) if current.lower() in it["name"].lower()][:25]

    @app_commands.command(name="buy", description="💎 Achète un objet de la boutique")
    @app_commands.autocomplete(objet=_item_autocomplete)
    @app_commands.guild_only()
    async def buy(self, interaction: discord.Interaction, objet: str) -> None:
        if not await self._enabled(interaction) or not await require(interaction, "La boutique"):
            return
        item = next((it for it in self.shop_items(interaction.guild) if it["name"].lower() == objet.lower()), None)
        member = interaction.user
        assert isinstance(member, discord.Member) and interaction.guild
        if not item:
            await reply_error(interaction, "Objet introuvable. Regarde la liste avec `/shop`.")
            return
        role = interaction.guild.get_role(int(item.get("role") or 0))
        if role and role in member.roles:
            await reply_error(interaction, f"Tu as déjà le rôle {role.mention}.")
            return
        if role and role >= interaction.guild.me.top_role:
            await reply_error(interaction, "Je ne peux pas donner ce rôle (il est au-dessus du mien). Préviens le staff.")
            return
        price = int(item["price"])
        if not await self.spend(interaction.guild.id, member.id, price):
            await reply_error(interaction, f"Il te faut {money(interaction.guild, price)} pour acheter **{item['name']}**.")
            return
        if role:
            await member.add_roles(role, reason=f"Achat boutique : {item['name']}")
        await self.db.execute(
            "INSERT INTO inventory (guild_id, user_id, item, quantity) VALUES (?,?,?,1) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET quantity = quantity + 1",
            (interaction.guild.id, member.id, item["name"]))
        await interaction.response.send_message(embed=embeds.success(
            f"Tu as acheté **{item['name']}** pour {money(interaction.guild, price)}."
            + (f"\nTu as reçu le rôle {role.mention} !" if role else ""), "🛒 Achat"))

    @app_commands.command(name="inventory", description="💎 Ton inventaire (ou celui d'un membre)")
    @app_commands.guild_only()
    async def inventory(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        if not await self._enabled(interaction) or not await require(interaction, "L'inventaire"):
            return
        member = membre or interaction.user
        rows = await self.db.fetchall(
            "SELECT item, quantity FROM inventory WHERE guild_id=? AND user_id=? AND quantity > 0 ORDER BY item",
            (interaction.guild_id, member.id))
        text = "\n".join(f"• **{r['item']}** × {r['quantity']}" for r in rows) or "Inventaire vide."
        await interaction.response.send_message(embed=embeds.base(f"🎒 Inventaire de {member.display_name}", text,
                                                                  guild=interaction.guild))


def bank_rate(value) -> float:
    """Taux d'intérêt quotidien, borné entre 0 et 10 %."""
    try:
        return max(0.0, min(float(value), 10.0))
    except (TypeError, ValueError):
        return 0.0


def parse_amount(raw: str, available: int) -> int | None:
    """« 500 », « 1 000 », « tout » / « all » → montant (None si invalide)."""
    text = raw.strip().lower().replace(" ", "").replace("_", "")
    if text in ("tout", "all", "max"):
        return available if available > 0 else None
    if text.isdigit() and 0 < int(text) <= 10**12:
        return int(text)
    return None


def format_duration_s(seconds: float) -> str:
    from datetime import timedelta
    return format_duration(timedelta(seconds=max(1, int(seconds))))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
