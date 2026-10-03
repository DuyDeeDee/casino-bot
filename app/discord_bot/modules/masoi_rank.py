"""Rank settlement policy separated from Discord rendering and transport."""
from app.discord_bot.modules.masoi_engine import Faction


class MasoiRankService:
    @staticmethod
    def results(game):
        return [(uid, points, game.did_player_win(uid), game.get_rank_faction(uid).value)
                for uid, points in game.calculate_rank_points().items()
                if game.winner_faction != Faction.DRAW or game.did_player_win(uid)]

    @classmethod
    def settle(cls, game, economy):
        if not game.settings.enable_rank or not game.has_rankable_result():
            return False
        if economy is None:
            raise RuntimeError("Không có database để lưu rank Ma Sói")
        changed = economy.settle_masoi_match(game.rank_match_id, cls.results(game))
        game.rank_settled = True
        return changed
