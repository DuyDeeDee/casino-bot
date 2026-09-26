"""Rank settlement policy separated from Discord rendering and transport."""
from app.discord_bot.modules.masoi_engine import Faction


class MasoiRankService:
    @staticmethod
    def results(game):
        return [(uid, points, game.did_player_win(uid), game.get_rank_faction(uid).value)
                for uid, points in game.calculate_rank_points().items()]

    @classmethod
    def settle(cls, game, economy):
        if not game.winner_faction or not game.settings.enable_rank or game.winner_faction == Faction.DRAW:
            return False
        if economy is None:
            raise RuntimeError("Không có database để lưu rank Ma Sói")
        changed = economy.settle_masoi_match(game.rank_match_id, cls.results(game))
        game.rank_settled = True
        return changed
