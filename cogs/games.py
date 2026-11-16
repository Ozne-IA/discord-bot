"""Mini-jeux avec la monnaie du serveur.
Gratuit : /pileouface, /des, /devine, /quiz.   💎 Premium : /roulette, /blackjack."""
from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.i18n import language
from bot.premium import require
from bot.quiz_data import QUIZ_EN, QUIZ_FR
from bot.utils import reply_error
from cogs.economy import money

RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
SUITS = "♠♥♦♣"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


# --------------------------------------------------------------------------- #
#  Règles (fonctions pures, testées)
# --------------------------------------------------------------------------- #
def roulette_payout(bet: str, number: int) -> int:
    """Multiplicateur gagné (0 = perdu). bet : rouge, noir, pair, impair, ou un numéro 0-36."""
    if bet.isdigit():
        return 36 if int(bet) == number else 0
    if number == 0:
        return 0
    wins = {"rouge": number in RED, "noir": number not in RED,
            "pair": number % 2 == 0, "impair": number % 2 == 1}
    return 2 if wins.get(bet) else 0


def hand_value(cards: list[str]) -> int:
    total, aces = 0, 0
    for card in cards:
        rank = card[:-1]
        if rank == "A":
            total, aces = total + 11, aces + 1
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total, aces = total - 10, aces - 1
    return total


def new_deck(rng: random.Random | None = None) -> list[str]:
    deck = [r + s for s in SUITS for r in RANKS]
    (rng or random).shuffle(deck)
    return deck


def blackjack_result(player: list[str], dealer: list[str]) -> float:
    """Multiplicateur rendu au joueur : 2.5 blackjack naturel, 2 victoire, 1 égalité, 0 défaite."""
    p, d = hand_value(player), hand_value(dealer)
    if p > 21:
        return 0
    if p == 21 and len(player) == 2 and not (d == 21 and len(dealer) == 2):
        return 2.5
    if d > 21 or p > d:
        return 2
    return 1 if p == d else 0


# --------------------------------------------------------------------------- #
#  Blackjack interactif
# --------------------------------------------------------------------------- #
class BlackjackView(discord.ui.View):
    def __init__(self, cog: "Games", interaction: discord.Interaction, bet: int) -> None:
        super().__init__(timeout=120)
        self.cog, self.bet, self.owner = cog, bet, interaction.user.id
        self.guild = interaction.guild
        self.deck = new_deck()
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.message: discord.Message | None = None
        self.done = False

    def embed(self, reveal: bool = False, result: str | None = None) -> discord.Embed:
        dealer_cards = " ".join(self.dealer) if reveal else f"{self.dealer[0]} 🂠"
        dealer_value = hand_value(self.dealer) if reveal else "?"
        e = embeds.base("🃏 Blackjack", f"Mise : {money(self.guild, self.bet)}", guild=self.guild)
        e.add_field(name=f"Toi ({hand_value(self.player)})", value=" ".join(self.player))
        e.add_field(name=f"Croupier ({dealer_value})", value=dealer_cards)
        if result:
            e.add_field(name="Résultat", value=result, inline=False)
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message(embed=embeds.error("Ce n'est pas ta partie."), ephemeral=True)
            return False
        return True

    async def finish(self, interaction: discord.Interaction | None, initial: bool = False) -> None:
        self.done = True
        while hand_value(self.dealer) < 17 and hand_value(self.player) <= 21:
            self.dealer.append(self.deck.pop())
        mult = blackjack_result(self.player, self.dealer)
        payout = int(self.bet * mult)
        if payout:
            await self.cog.economy.add(self.guild.id, self.owner, payout)
        if mult > 1 and self.guild:
            member = self.guild.get_member(self.owner)
            if member:
                self.cog.won(self.guild, member, self.message.channel if self.message else
                             (interaction.channel if interaction else None))
        if mult == 0:
            result = f"💥 Perdu : -{money(self.guild, self.bet)}"
        elif mult == 1:
            result = "🤝 Égalité : ta mise t'est rendue."
        else:
            result = f"🎉 Gagné : +{money(self.guild, payout - self.bet)}" + (" (Blackjack !)" if mult == 2.5 else "")
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        embed = self.embed(reveal=True, result=result)
        if interaction and initial:
            await interaction.response.send_message(embed=embed, view=self)
        elif interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Tirer", emoji="➕", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.player.append(self.deck.pop())
        if hand_value(self.player) >= 21:
            await self.finish(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Rester", emoji="✋", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.finish(interaction)

    async def on_timeout(self) -> None:
        if not self.done:
            try:
                await self.finish(None)  # temps écoulé : on reste
            except discord.HTTPException:
                pass


# --------------------------------------------------------------------------- #
#  Devine le nombre / quiz
# --------------------------------------------------------------------------- #
class GuessModal(discord.ui.Modal, title="Devine le nombre"):
    guess = discord.ui.TextInput(label="Ton nombre (1 à 100)", max_length=3)

    def __init__(self, view: "GuessView") -> None:
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.view.play(interaction, str(self.guess))


class GuessView(discord.ui.View):
    MAX_TRIES = 7

    def __init__(self, cog: "Games", interaction: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.cog, self.owner, self.guild = cog, interaction.user.id, interaction.guild
        self.secret = random.randint(1, 100)
        self.tries: list[str] = []

    def embed(self, extra: str = "") -> discord.Embed:
        left = self.MAX_TRIES - len(self.tries)
        text = f"J'ai choisi un nombre entre **1** et **100**. Il te reste **{left}** essai(s)."
        if self.tries:
            text += "\n\n" + "\n".join(self.tries)
        if extra:
            text += "\n\n" + extra
        return embeds.base("🔢 Devine le nombre", text, guild=self.guild)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message(embed=embeds.error("Ce n'est pas ta partie."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Proposer un nombre", emoji="🔢", style=discord.ButtonStyle.primary)
    async def propose(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(GuessModal(self))

    async def play(self, interaction: discord.Interaction, raw: str) -> None:
        if not raw.strip().isdigit() or not 1 <= int(raw) <= 100:
            await interaction.response.send_message(embed=embeds.error("Donne un nombre entre 1 et 100."), ephemeral=True)
            return
        n = int(raw)
        if n == self.secret:
            reward = int(gconf(self.guild).get("games", "guess_reward", default=100))
            reward = max(1, reward * (self.MAX_TRIES - len(self.tries)) // self.MAX_TRIES)
            await self.cog.economy.add(self.guild.id, self.owner, reward)
            self.cog.won(self.guild, interaction.user, interaction.channel)
            self.tries.append(f"✅ **{n}**")
            self.stop()
            self.propose.disabled = True
            await interaction.response.edit_message(
                embed=self.embed(f"🎉 Bravo, c'était **{n}** ! Tu gagnes {money(self.guild, reward)}."), view=self)
            return
        self.tries.append(f"{'⬆️' if n < self.secret else '⬇️'} {n} — c'est {'plus' if n < self.secret else 'moins'}")
        if len(self.tries) >= self.MAX_TRIES:
            self.stop()
            self.propose.disabled = True
            await interaction.response.edit_message(embed=self.embed(f"😢 Perdu ! C'était **{self.secret}**."), view=self)
            return
        await interaction.response.edit_message(embed=self.embed(), view=self)


class QuizView(discord.ui.View):
    def __init__(self, cog: "Games", guild: discord.Guild, question: str, answers: list[str], correct: str) -> None:
        super().__init__(timeout=20)
        self.cog, self.guild, self.correct = cog, guild, correct
        self.question, self.answers = question, answers
        self.tried: set[int] = set()
        self.winner: discord.abc.User | None = None
        self.message: discord.Message | None = None
        for i, answer in enumerate(answers):
            button = discord.ui.Button(label=answer[:80], style=discord.ButtonStyle.secondary, emoji="🅰🅱🅲🅳"[i])
            button.callback = self._make(answer)
            self.add_item(button)

    def _make(self, answer: str):
        async def callback(interaction: discord.Interaction) -> None:
            if self.winner or interaction.user.id in self.tried:
                await interaction.response.send_message(embed=embeds.error("Tu as déjà répondu."), ephemeral=True)
                return
            self.tried.add(interaction.user.id)
            if answer != self.correct:
                await interaction.response.send_message(embed=embeds.error("Mauvaise réponse !"), ephemeral=True)
                return
            self.winner = interaction.user
            reward = int(gconf(self.guild).get("games", "quiz_reward", default=50))
            await self.cog.economy.add(self.guild.id, interaction.user.id, reward)
            self.cog.won(self.guild, interaction.user, interaction.channel)
            await interaction.response.edit_message(embed=self.result_embed(), view=self.closed())
            self.stop()
        return callback

    def closed(self) -> "QuizView":
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
            if getattr(item, "label", None) == self.correct[:80]:
                item.style = discord.ButtonStyle.success  # type: ignore[attr-defined]
        return self

    def result_embed(self) -> discord.Embed:
        if self.winner:
            reward = int(gconf(self.guild).get("games", "quiz_reward", default=50))
            text = f"✅ {self.winner.mention} a trouvé : **{self.correct}** (+{money(self.guild, reward)})"
        else:
            text = f"⏰ Temps écoulé ! La réponse était **{self.correct}**."
        return embeds.base(f"❓ {self.question}", text, guild=self.guild)

    async def on_timeout(self) -> None:
        self.cog.active_quiz.discard(self.message.channel.id if self.message else 0)
        if self.message and not self.winner:
            try:
                await self.message.edit(embed=self.result_embed(), view=self.closed())
            except discord.HTTPException:
                pass

    def stop(self) -> None:
        if self.message:
            self.cog.active_quiz.discard(self.message.channel.id)
        super().stop()


# --------------------------------------------------------------------------- #
#  Cog
# --------------------------------------------------------------------------- #
class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_quiz: set[int] = set()
        self.last_play: dict[tuple[int, int], float] = {}

    @property
    def economy(self):
        return self.bot.get_cog("Economy")

    async def _ready(self, interaction: discord.Interaction) -> bool:
        cfg = gconf(interaction.guild)
        if not (cfg.get("games", "enabled", default=True) and cfg.get("economy", "enabled", default=True)
                and self.economy):
            await reply_error(interaction, "Les mini-jeux (ou l'économie) sont désactivés sur ce serveur.")
            return False
        key = (interaction.guild_id or 0, interaction.user.id)
        if time.time() - self.last_play.get(key, 0) < 3:
            await reply_error(interaction, "Doucement ! Attends quelques secondes entre deux parties.")
            return False
        self.last_play[key] = time.time()
        self.bot.dispatch("activity", interaction.guild, interaction.user, interaction.channel, "game_play", 1)
        return True

    def won(self, guild: discord.Guild | None, user: discord.abc.User, channel) -> None:
        """Signale une victoire (quêtes et succès)."""
        self.bot.dispatch("activity", guild, user, channel, "game_win", 1)

    async def _take_bet(self, interaction: discord.Interaction, bet: int) -> bool:
        max_bet = int(gconf(interaction.guild).get("games", "max_bet", default=10000) or 0)
        if max_bet and bet > max_bet:
            await reply_error(interaction, f"Mise maximum sur ce serveur : {money(interaction.guild, max_bet)}.")
            return False
        if not await self.economy.spend(interaction.guild_id or 0, interaction.user.id, bet):
            await reply_error(interaction, f"Tu n'as pas assez d'argent pour miser {money(interaction.guild, bet)}.")
            return False
        return True

    @app_commands.command(name="pileouface", description="Parie sur pile ou face (×2 si tu gagnes)")
    @app_commands.choices(choix=[app_commands.Choice(name="🪙 Pile", value="pile"),
                                 app_commands.Choice(name="👑 Face", value="face")])
    @app_commands.guild_only()
    async def coinflip(self, interaction: discord.Interaction, mise: app_commands.Range[int, 1, 1_000_000_000],
                       choix: app_commands.Choice[str]) -> None:
        if not await self._ready(interaction) or not await self._take_bet(interaction, mise):
            return
        result = random.choice(["pile", "face"])
        icon = "🪙 Pile" if result == "pile" else "👑 Face"
        if result == choix.value:
            await self.economy.add(interaction.guild_id, interaction.user.id, mise * 2)
            self.won(interaction.guild, interaction.user, interaction.channel)
            text, color = f"{icon} ! Tu gagnes {money(interaction.guild, mise)} 🎉", embeds.SUCCESS
        else:
            text, color = f"{icon}… Tu perds {money(interaction.guild, mise)}.", embeds.ERROR
        await interaction.response.send_message(embed=embeds.base("🪙 Pile ou face", text, color=color))

    @app_commands.command(name="des", description="Lance les dés contre le bot (le plus grand total gagne ×2)")
    @app_commands.guild_only()
    async def dice(self, interaction: discord.Interaction, mise: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        if not await self._ready(interaction) or not await self._take_bet(interaction, mise):
            return
        you, bot_roll = [random.randint(1, 6) for _ in range(2)], [random.randint(1, 6) for _ in range(2)]
        a, b = sum(you), sum(bot_roll)
        if a > b:
            await self.economy.add(interaction.guild_id, interaction.user.id, mise * 2)
            self.won(interaction.guild, interaction.user, interaction.channel)
            result, color = f"🎉 Tu gagnes {money(interaction.guild, mise)} !", embeds.SUCCESS
        elif a == b:
            await self.economy.add(interaction.guild_id, interaction.user.id, mise)
            result, color = "🤝 Égalité : ta mise t'est rendue.", embeds.INFO
        else:
            result, color = f"💥 Tu perds {money(interaction.guild, mise)}.", embeds.ERROR
        text = f"🎲 Toi : **{you[0]} + {you[1]} = {a}**\n🤖 Bot : **{bot_roll[0]} + {bot_roll[1]} = {b}**\n\n{result}"
        await interaction.response.send_message(embed=embeds.base("🎲 Dés", text, color=color))

    @app_commands.command(name="devine", description="Devine le nombre entre 1 et 100 en 7 essais")
    @app_commands.guild_only()
    async def guess(self, interaction: discord.Interaction) -> None:
        if not await self._ready(interaction):
            return
        view = GuessView(self, interaction)
        await interaction.response.send_message(embed=view.embed(), view=view)

    @app_commands.command(name="quiz", description="Question de culture générale : le premier qui trouve gagne")
    @app_commands.guild_only()
    async def quiz(self, interaction: discord.Interaction) -> None:
        if not await self._ready(interaction):
            return
        if interaction.channel_id in self.active_quiz:
            await reply_error(interaction, "Un quiz est déjà en cours dans ce salon.")
            return
        assert interaction.guild
        bank = QUIZ_EN if language(interaction.guild) == "en" else QUIZ_FR
        question, correct, wrong = random.choice(bank)
        answers = [correct, *wrong]
        random.shuffle(answers)
        view = QuizView(self, interaction.guild, question, answers, correct)
        self.active_quiz.add(interaction.channel_id or 0)
        reward = int(gconf(interaction.guild).get("games", "quiz_reward", default=50))
        embed = embeds.base(f"❓ {question}", f"Le premier qui trouve gagne {money(interaction.guild, reward)}. "
                                              "Une seule réponse par personne ! ⏰ 20 secondes", guild=interaction.guild)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    # --- 💎 casino ----------------------------------------------------------
    @app_commands.command(name="roulette", description="💎 Roulette : rouge/noir/pair/impair (×2) ou un numéro (×36)")
    @app_commands.describe(pari="rouge, noir, pair, impair ou un numéro de 0 à 36")
    @app_commands.guild_only()
    async def roulette(self, interaction: discord.Interaction, mise: app_commands.Range[int, 1, 1_000_000_000],
                       pari: str) -> None:
        bet = pari.strip().lower()
        valid = bet in ("rouge", "noir", "pair", "impair", "red", "black", "even", "odd") \
            or (bet.isdigit() and 0 <= int(bet) <= 36)
        if not valid:
            await reply_error(interaction, "Pari invalide : `rouge`, `noir`, `pair`, `impair` ou un numéro de 0 à 36.")
            return
        bet = {"red": "rouge", "black": "noir", "even": "pair", "odd": "impair"}.get(bet, bet)
        if not await require(interaction, "La roulette") or not await self._ready(interaction) \
                or not await self._take_bet(interaction, mise):
            return
        number = random.randint(0, 36)
        color = "🟢" if number == 0 else ("🔴" if number in RED else "⚫")
        mult = roulette_payout(bet, number)
        landed = f"La bille tombe sur {color} **{number}**"
        if mult:
            await self.economy.add(interaction.guild_id, interaction.user.id, mise * mult)
            self.won(interaction.guild, interaction.user, interaction.channel)
            text, c = f"{landed} !\n🎉 Tu gagnes {money(interaction.guild, mise * (mult - 1))}", embeds.SUCCESS
        else:
            text, c = f"{landed}…\n💥 Tu perds {money(interaction.guild, mise)}.", embeds.ERROR
        await interaction.response.send_message(embed=embeds.base("🎡 Roulette", text, color=c))

    @app_commands.command(name="blackjack", description="💎 Blackjack contre le croupier")
    @app_commands.guild_only()
    async def blackjack(self, interaction: discord.Interaction, mise: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        if not await require(interaction, "Le blackjack") or not await self._ready(interaction) \
                or not await self._take_bet(interaction, mise):
            return
        view = BlackjackView(self, interaction, mise)
        if hand_value(view.player) == 21:  # blackjack naturel
            await view.finish(interaction, initial=True)
            return
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Games(bot))
