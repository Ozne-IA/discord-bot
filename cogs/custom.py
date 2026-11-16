"""Outils admin configurés dans le panel :
- commandes perso / réponses automatiques (5 en gratuit, 50 en 💎) ;
- menus de rôles perso à boutons ou menu déroulant (2 en gratuit, 15 en 💎) ;
- 💎 messages programmés (une fois, chaque jour ou chaque semaine)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf, limit_for
from bot.premium import is_premium
from bot.utils import fill_template

log = logging.getLogger("cogs.custom")
STEP = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
LATE_LIMIT = timedelta(hours=1)  # après une coupure, on n'envoie pas un message programmé avec plus d'1 h de retard


def guild_tz(guild: discord.Guild | int) -> ZoneInfo:
    name = gconf(guild).get("birthdays", "timezone", default="Europe/Paris") or "Europe/Paris"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Paris")


def due_occurrence(at: datetime, repeat: str, now: datetime) -> datetime | None:
    """Dernière occurrence prévue qui est passée (ou None si rien n'est encore dû)."""
    if now < at:
        return None
    if repeat not in STEP:
        return at
    steps = (now - at) // STEP[repeat]
    return at + steps * STEP[repeat]


def command_matches(cmd: dict, content: str) -> bool:
    text = content.strip().lower()
    return text == cmd["trigger"] if cmd["mode"] == "exact" else cmd["trigger"] in text


# --------------------------------------------------------------------------- #
#  Menus de rôles (boutons et menus persistants grâce à l'ID dans le custom_id)
# --------------------------------------------------------------------------- #
def find_menu(guild: discord.Guild, menu_id: str) -> tuple[dict | None, bool]:
    menus = gconf(guild).get("role_menus", default=[]) or []
    allowed = limit_for("role_menus", is_premium(guild))
    for i, menu in enumerate(menus):
        if menu["id"] == menu_id:
            return menu, i < allowed
    return None, False


async def apply_roles(interaction: discord.Interaction, menu_id: str, wanted_ids: set[int] | None, toggle: int | None) -> None:
    guild, member = interaction.guild, interaction.user
    assert guild and isinstance(member, discord.Member)
    menu, allowed = find_menu(guild, menu_id)
    if not menu:
        await interaction.response.send_message(embed=embeds.error("Ce menu n'existe plus."), ephemeral=True)
        return
    if not allowed:
        await interaction.response.send_message(embed=embeds.error(
            "Ce menu dépasse la limite de la version gratuite. Le staff doit passer en 💎 Premium ou supprimer un menu."),
            ephemeral=True)
        return
    menu_roles = {r["role"]: guild.get_role(r["role"]) for r in menu["roles"]}
    menu_roles = {k: v for k, v in menu_roles.items() if v and v < guild.me.top_role}
    current = {rid for rid in menu_roles if menu_roles[rid] in member.roles}
    if toggle is not None:
        if toggle not in menu_roles:
            await interaction.response.send_message(embed=embeds.error("Ce rôle n'est plus disponible."), ephemeral=True)
            return
        wanted = current ^ {toggle}
        if not menu.get("multiple", True) and toggle in wanted:
            wanted = {toggle}
    else:
        wanted = {rid for rid in (wanted_ids or set()) if rid in menu_roles}
    to_add = [menu_roles[r] for r in wanted - current]
    to_remove = [menu_roles[r] for r in current - wanted]
    if to_add:
        await member.add_roles(*to_add, reason=f"Menu de rôles {menu_id}")
    if to_remove:
        await member.remove_roles(*to_remove, reason=f"Menu de rôles {menu_id}")
    parts = []
    if to_add:
        parts.append("➕ " + ", ".join(r.mention for r in to_add))
    if to_remove:
        parts.append("➖ " + ", ".join(r.mention for r in to_remove))
    await interaction.response.send_message(embed=embeds.success("\n".join(parts) or "Aucun changement."), ephemeral=True)


class RoleMenuButton(discord.ui.DynamicItem[discord.ui.Button], template=r"rolemenu:(?P<menu>[a-z0-9]+):(?P<role>\d+)"):
    def __init__(self, menu_id: str, role_id: int, label: str = "", emoji: str | None = None) -> None:
        super().__init__(discord.ui.Button(label=label[:80] or None, emoji=emoji or None,
                                           style=discord.ButtonStyle.secondary, custom_id=f"rolemenu:{menu_id}:{role_id}"))
        self.menu_id, self.role_id = menu_id, role_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["menu"], int(match["role"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await apply_roles(interaction, self.menu_id, None, self.role_id)


class RoleMenuSelect(discord.ui.DynamicItem[discord.ui.Select], template=r"rolemenus:(?P<menu>[a-z0-9]+)"):
    def __init__(self, menu_id: str, options: list[discord.SelectOption] | None = None, multiple: bool = True,
                 placeholder: str = "Choisis tes rôles…") -> None:
        options = options or [discord.SelectOption(label="…", value="0")]
        super().__init__(discord.ui.Select(custom_id=f"rolemenus:{menu_id}", options=options, min_values=0,
                                           max_values=len(options) if multiple else 1, placeholder=placeholder))
        self.menu_id = menu_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["menu"])

    async def callback(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", []) if interaction.data else []  # type: ignore[union-attr]
        await apply_roles(interaction, self.menu_id, {int(v) for v in values if str(v).isdigit()}, None)


def build_role_menu(guild: discord.Guild, menu: dict) -> tuple[discord.Embed, discord.ui.View]:
    lines = []
    for r in menu["roles"]:
        role = guild.get_role(r["role"])
        if role:
            lines.append(f"{r.get('emoji') or '•'} {role.mention}" + (f" — {r['label']}" if r.get("label") else ""))
    description = (menu.get("description") or "") + ("\n\n" if menu.get("description") and lines else "") + "\n".join(lines)
    embed = embeds.base(menu.get("title") or "🎭 Rôles", description or None, guild=guild)
    view = discord.ui.View(timeout=None)
    if menu.get("style") == "select":
        options = []
        for r in menu["roles"][:25]:
            role = guild.get_role(r["role"])
            if role:
                options.append(discord.SelectOption(label=(r.get("label") or role.name)[:100], value=str(role.id),
                                                    emoji=r.get("emoji") or None))
        if options:
            view.add_item(RoleMenuSelect(menu["id"], options, menu.get("multiple", True)))
    else:
        for r in menu["roles"][:25]:
            role = guild.get_role(r["role"])
            if role:
                view.add_item(RoleMenuButton(menu["id"], role.id, r.get("label") or role.name, r.get("emoji")))
    return embed, view


async def publish_role_menu(bot, guild: discord.Guild, menu: dict) -> discord.Message:
    channel = guild.get_channel(int(menu.get("channel") or 0))
    if not isinstance(channel, discord.TextChannel):
        raise ValueError("Choisis le salon du menu.")
    embed, view = build_role_menu(guild, menu)
    key = f"role_menu:{menu['id']}"
    previous = await bot.db.get_setting(guild.id, key)
    if previous:
        ch_id, msg_id = previous.split(":", 1)
        if int(ch_id) == channel.id:
            try:
                message = await channel.fetch_message(int(msg_id))
                await message.edit(embed=embed, view=view)
                return message
            except discord.HTTPException:
                pass
    message = await channel.send(embed=embed, view=view)
    await bot.db.set_setting(guild.id, key, f"{channel.id}:{message.id}")
    return message


def custom_embed(guild: discord.Guild, title: str, message: str) -> discord.Embed:
    return embeds.base(title or None, message or None, guild=guild)


# --------------------------------------------------------------------------- #
#  Cog
# --------------------------------------------------------------------------- #
class Custom(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns: dict[tuple[int, str], float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(RoleMenuButton, RoleMenuSelect)
        self.scheduler.start()

    async def cog_unload(self) -> None:
        self.scheduler.cancel()
        self.bot.remove_dynamic_items(RoleMenuButton, RoleMenuSelect)

    # --- commandes perso ---------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member) or not message.content:
            return
        cmds = (gconf(message.guild).get("custom_commands", default=[]) or [])
        cmds = cmds[:limit_for("custom_commands", is_premium(message.guild))]
        cmd = next((c for c in cmds if command_matches(c, message.content)), None)
        if not cmd:
            return
        key = (message.channel.id, cmd["trigger"])
        if time.time() - self.cooldowns.get(key, 0) < 5:  # anti-spam : 5 s par salon et par commande
            return
        self.cooldowns[key] = time.time()
        text = fill_template(cmd["response"], message.author)
        try:
            if cmd.get("embed"):
                await message.channel.send(embed=embeds.base(None, text, guild=message.guild),
                                           allowed_mentions=discord.AllowedMentions(users=True))
            else:
                await message.channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            pass

    # --- 💎 messages programmés -------------------------------------------
    @tasks.loop(seconds=30)
    async def scheduler(self) -> None:
        for guild in self.bot.guilds:
            items = gconf(guild).get("scheduled", default=[]) or []  # vide si le serveur n'est pas Premium
            if not items:
                continue
            tz = guild_tz(guild)
            now = datetime.now(tz)
            for item in items:
                try:
                    at = datetime.strptime(item["at"], "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
                except ValueError:
                    continue
                occurrence = due_occurrence(at, item["repeat"], now)
                if occurrence is None or now - occurrence > LATE_LIMIT:
                    continue
                key = f"scheduled_last:{item['id']}"
                if await self.db.get_setting(guild.id, key) == occurrence.isoformat():
                    continue
                await self.db.set_setting(guild.id, key, occurrence.isoformat())
                channel = guild.get_channel(int(item["channel"]))
                if not isinstance(channel, discord.TextChannel):
                    continue
                mention = {"everyone": "@everyone", "here": "@here"}.get(item.get("mention", "none"))
                try:
                    await channel.send(content=mention, embed=custom_embed(guild, item["title"], item["message"]),
                                       allowed_mentions=discord.AllowedMentions(everyone=bool(mention)))
                except discord.HTTPException as exc:
                    log.info("Message programmé %s non envoyé : %s", item["id"], exc)

    @scheduler.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Custom(bot))
