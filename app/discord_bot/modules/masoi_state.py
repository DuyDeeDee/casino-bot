"""Versioned, JSON-only snapshots. Never serialize Discord objects or use pickle.

Interrupted matches are cancelled safely, not resumed with incomplete private UI.
Completed results may be retried using the original idempotent match ID.
"""
from __future__ import annotations
import time
import discord
from app.discord_bot.modules.masoi_engine import (
    ActionIntent, ActionKind, Faction, GamePhase, MasoiGame, MasoiPlayer,
    MasoiSettings, NightEvent, NightResult, ReplayLog, Role,
)
from app.discord_bot.modules.masoi_rank import MasoiRankService


def snapshot_game(game):
    players = []
    for player in game.players.values():
        fields = {key: value for key, value in vars(player).items()
                  if value is None or type(value) in (str, int, float, bool)}
        fields["role"] = player.role.name
        players.append(fields)
    permissions = []
    for uid, overwrite in game.channel_permission_snapshots.items():
        pair = None if overwrite is None else [value.value for value in overwrite.pair()]
        permissions.append({"user_id": uid, "overwrite": pair})
    def intents(values):
        return [{"night": a.night, "actor_id": a.actor_id, "kind": a.kind.name, "targets": list(a.targets)} for a in values]
    return {
        "version": 1, "match_id": game.rank_match_id,
        "guild_id": game.guild_id, "channel_id": game.channel_id,
        "host_id": game.host_id, "host_name": game.host_name, "message_id": game.message_id,
        "phase": game.phase.name, "start_time": game.start_time, "end_time": game.end_time,
        "night_count": game.night_count, "day_count": game.day_count,
        "deadline_at": time.time() + max(0, game.night_deadline - time.monotonic()) if game.night_deadline else None,
        "night_seed": game.night_seed,
        "event": game.current_night_event.name if game.current_night_event else None,
        "settings": game.settings.to_dict(), "players": players, "join_order": list(game.join_order),
        "winner": game.winner_faction.name if game.winner_faction else None,
        "rank_results": MasoiRankService.results(game) if game.has_rankable_result() and game.settings.enable_rank else [],
        "rank_settled": bool(getattr(game, "rank_settled", False)),
        "result_announced": bool(getattr(game, "result_announced", False)),
        "recovery_notified": bool(getattr(game, "recovery_notified", False)),
        "tanner_winner_id": game.tanner_winner_id, "mayor_id": game.mayor_id,
        "permissions": permissions,
        "intents": intents(game._night_intents.values()),
        "locked_intents": intents(game._locked_intents) if game._locked_intents is not None else None,
        "night_result": vars(game._night_result) if game._night_result is not None else None,
        "day_votes": dict(game.day_votes), "early_vote_requests": sorted(game.early_vote_requests),
        "replay": [dict(vars(log)) for log in game.replay_logs],
    }


def restore_game(data):
    if data.get("version") != 1:
        raise ValueError("Unsupported Ma Sói snapshot version")
    game = MasoiGame(data["guild_id"], data["channel_id"], data["host_id"], data["host_name"])
    game.rank_match_id = data["match_id"]
    game.phase = GamePhase[data["phase"]]
    game.settings = MasoiSettings.from_dict(data["settings"])
    for fields in data["players"]:
        player = MasoiPlayer(fields["user_id"], fields["display_name"])
        for key, value in fields.items():
            if key == "role":
                player.role = Role[value]
            elif key in vars(player) or key in ("mayor_passed_succession", "boss_lives", "boss_poison_shield"):
                # Preserve retired Boss fields only while reading archived/pending snapshots.
                setattr(player, key, value)
        game.players[player.user_id] = player
    game.join_order = list(data["join_order"])
    for key in ("message_id", "night_count", "day_count", "night_seed", "start_time", "end_time", "mayor_id", "tanner_winner_id", "rank_settled", "result_announced", "recovery_notified"):
        setattr(game, key, data.get(key))
    game.winner_faction = Faction[data["winner"]] if data.get("winner") else None
    game.current_night_event = NightEvent[data["event"]] if data.get("event") else None
    for entry in data["permissions"]:
        pair = entry["overwrite"]
        overwrite = None if pair is None else discord.PermissionOverwrite.from_pair(discord.Permissions(pair[0]), discord.Permissions(pair[1]))
        game.channel_permission_snapshots[entry["user_id"]] = overwrite
    def intent(item):
        return ActionIntent(item["night"], item["actor_id"], ActionKind[item["kind"]], tuple(item["targets"]))
    game._night_intents = {(a.actor_id, a.kind): a for a in map(intent, data["intents"])}
    game._locked_intents = tuple(map(intent, data["locked_intents"])) if data["locked_intents"] is not None else None
    result = data.get("night_result")
    if result:
        game._night_result = NightResult(result["night"], result["seed"], tuple(result["deaths"]), tuple(result["wolf_targets"]),
                                        tuple(tuple(row) for row in result["outcomes"]), tuple(result["pending_hunters"]), result["pending_mayor"])
    game.day_votes = {int(uid): target for uid, target in data["day_votes"].items()}
    game.early_vote_requests = set(data["early_vote_requests"])
    for fields in data["replay"]:
        timestamp = fields.get("timestamp")
        log = ReplayLog(**{key: value for key, value in fields.items() if key != "timestamp"})
        log.timestamp = timestamp
        game.replay_logs.append(log)
    # Monotonic timestamps cannot survive restart. No private action window is reopened.
    game.night_deadline = 0.0
    return game
