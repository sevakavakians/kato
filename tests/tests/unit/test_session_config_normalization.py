"""`use_token_matching` and `sort_symbols` must agree, whichever endpoint is used.

The two settings are not independent: token-level matching compares sorted
symbols, character-level matching compares the event as written. Supplying one
without the other derives the missing half.

That derivation used to live inline in the config-update endpoint only, so an
identical request body produced different configuration depending on which
endpoint received it -- `POST /sessions` with `use_token_matching: false` left
`sort_symbols` true, while `POST /sessions/{id}/config` set it false. These tests
pin the shared behaviour both now call.
"""

from types import SimpleNamespace

import pytest

from kato.config.configuration_service import ConfigurationService


def _settings():
    """Minimal stand-in for Settings; only the fields get_default_configuration reads."""
    return SimpleNamespace(
        learning=SimpleNamespace(
            max_pattern_length=0,
            persistence=5,
            recall_threshold=0.1,
            stm_mode='CLEAR',
        ),
        processing=SimpleNamespace(
            indexer_type='VI',
            max_predictions=100,
            sort_symbols=True,
            process_predictions=True,
            use_token_matching=True,
            rank_sort_algo='potential',
            fuzzy_token_threshold=0.0,
        ),
    )


@pytest.fixture
def service():
    return ConfigurationService(_settings())


# --- derivation ------------------------------------------------------------

@pytest.mark.parametrize("token_matching", [True, False])
def test_sort_symbols_derived_from_token_matching(service, token_matching):
    """Supplying the matching mode alone settles the sorting that goes with it."""
    out = service.normalize_session_config({'use_token_matching': token_matching})
    assert out['sort_symbols'] is token_matching


def test_derivation_is_identical_on_create_and_update(service):
    """The regression this exists for.

    Create passes no `current`; update passes the session's effective config.
    The same body must land on the same pair either way.
    """
    body = {'use_token_matching': False}

    on_create = service.normalize_session_config(body)
    on_update = service.normalize_session_config(
        body, current={'use_token_matching': True, 'sort_symbols': True}
    )

    assert on_create['sort_symbols'] == on_update['sort_symbols'] is False


def test_explicit_sort_symbols_is_never_overridden(service):
    """A caller that states both keeps what it asked for.

    Character-level matching over sorted symbols is occasionally deliberate, and
    silently correcting it would make the stated configuration a lie.
    """
    out = service.normalize_session_config(
        {'use_token_matching': False, 'sort_symbols': True}
    )
    assert out['use_token_matching'] is False
    assert out['sort_symbols'] is True


def test_sort_symbols_alone_does_not_change_the_matching_mode(service):
    """The pairing is one-directional.

    `use_token_matching` selects the algorithm; `sort_symbols` follows from it.
    Inferring the algorithm from a sorting flag would be a surprising thing for
    that flag to do, so it is left alone.
    """
    out = service.normalize_session_config({'sort_symbols': False})
    assert 'use_token_matching' not in out


def test_unrelated_fields_are_untouched(service):
    """Normalization must not disturb anything else in the payload."""
    body = {'recall_threshold': 0.4, 'max_predictions': 7, 'filter_pipeline': ['minhash']}
    assert service.normalize_session_config(body) == body


def test_input_is_not_mutated(service):
    """The caller's dict is reused afterwards; returning a copy keeps that safe."""
    body = {'use_token_matching': False}
    service.normalize_session_config(body)
    assert body == {'use_token_matching': False}, "caller's dict was mutated"


def test_empty_config_is_a_no_op(service):
    assert service.normalize_session_config({}) == {}


# --- mismatch warning ------------------------------------------------------

def test_conflicting_pair_warns(service, caplog):
    with caplog.at_level("WARNING"):
        service.normalize_session_config(
            {'use_token_matching': True, 'sort_symbols': False}
        )
    assert any("mismatch" in r.message.lower() for r in caplog.records)


def test_mismatch_against_stored_value_warns(service, caplog):
    """The hole the old inline check left open.

    It only fired when both fields arrived together. Setting `sort_symbols`
    alone, against an opposing value already on the session, produced an
    inconsistent configuration in silence.
    """
    with caplog.at_level("WARNING"):
        service.normalize_session_config(
            {'sort_symbols': True},
            current={'use_token_matching': False, 'sort_symbols': False},
        )
    assert any("mismatch" in r.message.lower() for r in caplog.records)


def test_mismatch_against_defaults_warns_on_create(service, caplog):
    """With no `current`, system defaults are the baseline.

    Defaults are token-matching with sorting on, so `sort_symbols: false` alone
    at creation is an effective mismatch and should say so.
    """
    with caplog.at_level("WARNING"):
        service.normalize_session_config({'sort_symbols': False})
    assert any("mismatch" in r.message.lower() for r in caplog.records)


@pytest.mark.parametrize("body", [
    {'use_token_matching': True},
    {'use_token_matching': False},
    {'use_token_matching': True, 'sort_symbols': True},
    {'use_token_matching': False, 'sort_symbols': False},
    {},
    {'recall_threshold': 0.4},
])
def test_agreeing_configurations_do_not_warn(service, body, caplog):
    """A derived pair agrees by construction, so it must stay quiet.

    A warning on the ordinary path would train readers to ignore the log, which
    costs more than the check is worth.
    """
    with caplog.at_level("WARNING"):
        service.normalize_session_config(body)
    assert [r.message for r in caplog.records if "mismatch" in r.message.lower()] == []
