"""Traduction automatique FR → EN des messages du bot."""
import discord

from bot.translate import translate, translate_embed, translate_view


def test_exact_and_templates():
    assert translate("Réservé au staff.") == "Staff only."
    assert translate("Ton ticket est ouvert : <#123>") == "Your ticket is open: <#123>"
    assert translate("<@1> a été averti (cas #12).\nRaison : spam\nTotal : **3**") == \
        "<@1> has been warned (case #12).\nReason: spam\nTotal: **3**"


def test_variable_parts_are_translated_too():
    assert translate("<@1> a été banni définitivement (cas #4).") == "<@1> has been banned permanently (case #4)."
    assert translate("Anniversaire enregistré : **15 novembre** 🎂") == "Birthday saved: **15 November** 🎂"


def test_multiline_fallback_and_unknown_text():
    text = "Ce serveur utilise la version **gratuite**.\n\nAvec **Premium** :\n• 🎉 Giveaways et 📊 sondages"
    assert translate(text) == "This server uses the **free** version.\n\nWith **Premium**:\n• 🎉 Giveaways and 📊 polls"
    assert translate("Texte personnalisé par un admin") == "Texte personnalisé par un admin"
    assert translate("") == "" and translate(None) is None


def test_embed_and_view_translation():
    e = discord.Embed(title="🛒 Boutique", description="Achète avec `/buy <objet>`.")
    e.add_field(name="Priorité", value="🟡 normale")
    translate_embed(e)
    assert e.title == "🛒 Shop" and e.description == "Buy with `/buy <item>`."
    assert e.fields[0].name == "Priority"
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Prendre en charge"))
    translate_view(view)
    assert view.children[0].label == "Claim"
