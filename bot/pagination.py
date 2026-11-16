"""Vue de pagination réutilisable (leaderboard, historique, etc.)."""
from __future__ import annotations

import discord


class Paginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.pages = pages or [discord.Embed(description="Rien à afficher.")]
        self.index = 0
        self.author_id = author_id
        self.message: discord.Message | None = None
        self._refresh()

    def _refresh(self) -> None:
        last = len(self.pages) - 1
        self.first_page.disabled = self.prev_page.disabled = self.index == 0
        self.next_page.disabled = self.last_page.disabled = self.index >= last
        self.counter.label = f"{self.index + 1}/{len(self.pages)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seule la personne qui a lancé la commande peut tourner les pages.", ephemeral=True)
            return False
        return True

    async def _go(self, interaction: discord.Interaction, index: int) -> None:
        self.index = max(0, min(index, len(self.pages) - 1))
        self._refresh()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._go(interaction, 0)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._go(interaction, self.index - 1)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(self, interaction: discord.Interaction, _: discord.ui.Button):
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._go(interaction, self.index + 1)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._go(interaction, len(self.pages) - 1)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @classmethod
    async def send(cls, interaction: discord.Interaction, pages: list[discord.Embed],
                   ephemeral: bool = False) -> None:
        view = cls(pages, interaction.user.id)
        if len(view.pages) == 1:
            await interaction.response.send_message(embed=view.pages[0], ephemeral=ephemeral)
            return
        await interaction.response.send_message(embed=view.pages[0], view=view, ephemeral=ephemeral)
        view.message = await interaction.original_response()


def chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]
