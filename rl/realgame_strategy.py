"""Bridge that lets a trained PPO model take a turn inside CampaignGame.py.

Usage in CampaignGame.calcAImove:
    from rl import realgame_strategy
    if strategy_name == 'NeuralPPO':
        fundraising = realgame_strategy.act(player)
        calcEndTurn(fundraising)
        _ai_advance_turn()
        return

The model is loaded lazily and cached. The default model path can be
overridden via the env var CAMPAIGN_RL_MODEL.
"""
import os
import random

from . import obs as _obs
from . import actions as _actions
from .realgame_adapter import RealGameSimView


_model = None
_model_path_loaded = None


def _default_model_path():
    return os.environ.get(
        'CAMPAIGN_RL_MODEL',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'runs', 'v17_decoder_fixed', 'model'),
    )


def _ensure_model(model_path=None):
    """Lazy-load the PPO model. Imports stable-baselines3 only on first call,
    so the rest of the game runs fine when no neural strategy is selected."""
    global _model, _model_path_loaded
    path = model_path or _default_model_path()
    if _model is not None and _model_path_loaded == path:
        return _model
    from stable_baselines3 import PPO
    _model = PPO.load(path, device='cpu')
    _model_path_loaded = path
    return _model


def _get_campaign_game_module():
    """Find the live CampaignGame module — could be loaded as __main__ (when
    the user runs `python CampaignGame.py`) or as `CampaignGame` (when
    imported from a test). Falls back to importing as a module."""
    import sys
    main_mod = sys.modules.get('__main__')
    if main_mod is not None and hasattr(main_mod, 'calcAImove'):
        return main_mod
    import CampaignGame as cg
    return cg


def act(real_player_idx, model_path=None):
    """Take one turn for `real_player_idx` (1-based, as used by CampaignGame).

    Returns the fundraising hours to pass to calcEndTurn. Mutates the
    game's State / District / Player objects in place (org spend, ad
    spend, campaigning hours).
    """
    cg = _get_campaign_game_module()

    model = _ensure_model(model_path)
    rng = random.Random(0xBEEF * real_player_idx + cg.currentDate * 7919)
    sim_view = RealGameSimView.from_module(cg, rng=rng)
    # Find this player's position in the (sorted) adapter player list — this
    # is robust to non-contiguous or 0-indexed key schemes.
    try:
        p_idx = sim_view._player_keys.index(real_player_idx)
    except ValueError:
        raise RuntimeError(
            f'player {real_player_idx} not found in players_dict '
            f'(keys present: {sim_view._player_keys})')

    # Surface org investments AND post-turn spend breakdown to stdout so
    # the user can see exactly where the neural agent is allocating —
    # any state with non-zero spend and org=0 will print a [LEAK] tag.
    _actions.set_log_org_builds(True)
    _actions.set_log_spend(True)

    obs_vec = _obs.encode_obs(sim_view, agent_idx=p_idx)
    action, _ = model.predict(obs_vec, deterministic=True)

    # Dispatch on the model's action-space shape — Box with 53 floats is
    # the v12+ coupled space; Box with 151 is the original continuous;
    # MultiDiscrete is the discrete bootstrap.
    from gymnasium.spaces import Box
    if isinstance(model.action_space, Box):
        if model.action_space.shape[0] == _actions.COUPLED_ACTION_DIM:
            fundraising = _actions.decode_coupled_action(sim_view, p_idx, action)
        else:
            fundraising = _actions.decode_continuous_action(sim_view, p_idx, action)
    else:
        fundraising = _actions.decode_action(sim_view, p_idx, action)
    return int(fundraising)
