"""Test del caricamento delle card (__init__.py): percorsi serviti dalla cartella
dell'integrazione, registrazione automatica e rimozione delle vecchie copie.

Eseguibili con:  python tests/test_frontend.py   oppure   pytest tests/
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ha_stubs as stubs  # noqa: E402

stubs.install()
from _loader import load  # noqa: E402

const, integration = load("const", "__init__")


class Http:
    def __init__(self):
        self.paths = []

    async def async_register_static_paths(self, configs):
        self.paths.extend(configs)


class Config:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, rel):
        return str(self.root / rel)


def make_hass(root):
    hass = stubs.FakeHass()
    hass.http = Http()
    hass.config = Config(root)
    hass.extra_js = []

    async def run_in_executor(fn, *args):
        return fn(*args)

    hass.async_add_executor_job = run_in_executor
    return hass


def test_cards_served_from_integration_folder_with_version():
    with tempfile.TemporaryDirectory() as root:
        hass = make_hass(root)
        assert asyncio.run(integration.async_setup(hass, {})) is True
        by_url = {p.url_path: p for p in hass.http.paths}
        versioned = f"/chronotask/{const.INTEGRATION_VERSION}"
        assert set(by_url) == {versioned, "/local/chronotask"}
        assert by_url[versioned].cache_headers is True                 # cambia a ogni versione: può stare in cache
        assert by_url["/local/chronotask"].cache_headers is False      # vecchie risorse manuali: senza cache
        assert Path(by_url[versioned].path) == const.FRONTEND_DIR == Path(by_url["/local/chronotask"].path)
        for name in (*const.FRONTEND_FILES, const.FRONTEND_COMMON):
            assert (const.FRONTEND_DIR / name).is_file(), name           # i file esistono davvero nel pacchetto
        assert hass.extra_js == [f"{versioned}/{n}" for n in const.FRONTEND_FILES]
        assert not (Path(root) / "www").exists()                         # nessuna copia in <config>/www


def test_legacy_copies_removed_only_ours():
    with tempfile.TemporaryDirectory() as root:
        legacy = Path(root) / "www" / "chronotask"
        legacy.mkdir(parents=True)
        for name in (*const.FRONTEND_FILES, const.FRONTEND_COMMON):
            (legacy / name).write_text("vecchio")
        (legacy / "mio-file.js").write_text("dell'utente")
        asyncio.run(integration.async_setup(make_hass(root), {}))
        assert sorted(p.name for p in legacy.iterdir()) == ["mio-file.js"]   # i file dell'utente restano
        assert legacy.is_dir()


def test_legacy_folder_removed_when_empty():
    with tempfile.TemporaryDirectory() as root:
        legacy = Path(root) / "www" / "chronotask"
        legacy.mkdir(parents=True)
        for name in const.FRONTEND_FILES:                                  # versione vecchia: senza common
            (legacy / name).write_text("vecchio")
        asyncio.run(integration.async_setup(make_hass(root), {}))
        assert not legacy.exists() and (Path(root) / "www").is_dir()       # tolta solo la nostra cartella


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok ", name)
    print(f"{n} test passati")
