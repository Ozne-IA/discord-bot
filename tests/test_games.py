"""Règles des mini-jeux."""
import random

from bot.quiz_data import QUIZ_EN, QUIZ_FR
from cogs.games import blackjack_result, hand_value, new_deck, roulette_payout


def test_hand_value_with_aces():
    assert hand_value(["A♠", "K♥"]) == 21
    assert hand_value(["A♠", "A♥", "9♦"]) == 21
    assert hand_value(["K♠", "Q♥", "5♦"]) == 25
    assert hand_value(["A♠", "A♥", "A♦", "A♣"]) == 14


def test_blackjack_results():
    assert blackjack_result(["A♠", "K♥"], ["9♠", "9♥"]) == 2.5      # blackjack naturel
    assert blackjack_result(["A♠", "K♥"], ["A♦", "Q♣"]) == 1        # deux blackjacks
    assert blackjack_result(["10♠", "9♥"], ["10♦", "8♣"]) == 2
    assert blackjack_result(["10♠", "8♥"], ["10♦", "8♣"]) == 1
    assert blackjack_result(["10♠", "5♥", "9♦"], ["10♦", "8♣"]) == 0  # le joueur saute
    assert blackjack_result(["10♠", "7♥"], ["10♦", "6♣", "9♠"]) == 2  # le croupier saute


def test_deck_is_complete():
    deck = new_deck(random.Random(1))
    assert len(deck) == 52 and len(set(deck)) == 52


def test_roulette_payouts():
    assert roulette_payout("rouge", 1) == 2 and roulette_payout("noir", 1) == 0
    assert roulette_payout("pair", 2) == 2 and roulette_payout("impair", 2) == 0
    assert roulette_payout("rouge", 0) == 0 and roulette_payout("pair", 0) == 0  # le zéro fait perdre
    assert roulette_payout("17", 17) == 36 and roulette_payout("17", 18) == 0


def test_quiz_banks_are_valid():
    for bank in (QUIZ_FR, QUIZ_EN):
        assert len(bank) >= 20
        for question, correct, wrong in bank:
            assert question and correct and len(wrong) == 3 and correct not in wrong
