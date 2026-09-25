"""Named Magic Cap 68k interface profiles used by the package tools."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERFACES = ROOT / 'sdk/68k/interfaces'

PROFILES = {
    '1.0-original': INTERFACES / '1.0-original',
    '1.0': INTERFACES / '1.0',
    '1.5': INTERFACES / '1.5',
    'universal': INTERFACES / 'universal',
}


def resolve(name):
    """Return an interface directory for a profile name or explicit path."""
    path = Path(name)
    if path.exists():
        return path.resolve()
    try:
        result = PROFILES[name.lower()]
    except KeyError as error:
        choices = ', '.join(PROFILES)
        raise ValueError(f'unknown profile {name!r}; choose {choices} or a path') from error
    if not result.is_dir():
        raise FileNotFoundError(f'interface profile is not present: {result}')
    return result


def header_directories(interfaces):
    """Header roots for both the original nested and later flat layouts."""
    interfaces = Path(interfaces)
    candidates = [interfaces, interfaces / 'NoDebug',
                  interfaces / 'Device/Universal/NoDebug']
    # The later profiles share generated system-interface headers.
    if interfaces.parent == INTERFACES and interfaces != PROFILES['1.0-original']:
        candidates.append(INTERFACES / 'system')
    return tuple(path for path in candidates if path.is_dir())
