"""Carica i moduli puri di ChronoTask (const, slots) senza Home Assistant.

custom_components/chronotask/__init__.py importa HA, quindi il pacchetto non si
può importare normalmente nei test: qui si crea un pacchetto finto 'ct' che punta
alla cartella reale e si caricano solo i moduli senza dipendenze da HA.
"""
import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "chronotask"


def load(*names, pkg="ct"):
    if pkg not in sys.modules:
        p = types.ModuleType(pkg)
        p.__path__ = [str(PKG_DIR)]
        sys.modules[pkg] = p
    out = []
    for name in names:
        full = f"{pkg}.{name}"
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{name}.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[full] = mod
            spec.loader.exec_module(mod)
        out.append(sys.modules[full])
    return out[0] if len(out) == 1 else out
