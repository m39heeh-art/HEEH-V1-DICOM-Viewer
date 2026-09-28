import inspect
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.i18n as i18n

ALLOWED_KEYS = {"en", "ar"}


def _translation_dicts():
    """Yield (name, value) for module-level dicts that are translation maps."""
    for name, val in inspect.getmembers(i18n):
        if name.startswith("_"):
            continue
        if isinstance(val, dict) and "en" in val and "ar" in val:
            yield name, val


def test_all_translation_dicts_have_en_and_ar():
    count = 0
    for name, d in _translation_dicts():
        assert "en" in d, f"{name} missing 'en'"
        assert "ar" in d, f"{name} missing 'ar'"
        count += 1
    assert count > 0, "No translation dicts found"


def test_translation_values_are_nonempty_strings():
    for name, d in _translation_dicts():
        for lang, val in d.items():
            assert isinstance(val, str), f"{name}[{lang!r}] is not str"
            assert len(val) > 0, f"{name}[{lang!r}] is empty"


def test_translation_keys_are_only_en_ar():
    for name, d in _translation_dicts():
        extra = set(d.keys()) - ALLOWED_KEYS
        assert not extra, f"{name} has unexpected keys: {extra}"


def test_non_dict_constants_not_broken():
    """Ensure non-dict constants (LANGUAGES, RTL_LANGS) exist and are accessible."""
    assert hasattr(i18n, "LANGUAGES")
    assert isinstance(i18n.LANGUAGES, dict)
    assert hasattr(i18n, "RTL_LANGS")
    assert isinstance(i18n.RTL_LANGS, (set, list, dict, frozenset))
