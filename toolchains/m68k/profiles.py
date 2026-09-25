"""Named Magic Cap 68k interface profiles used by the package tools."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CW7 = ROOT / (
    'software/68k/extracted/CW7-Magic-MPW/CodeWarrior Magic%2FMPW Installer/'
    'MagicDeveloper/Interfaces')
CW8 = ROOT / (
    'software/68k/extracted/CW8_Gold_Tools_199601/Metrowerks CodeWarrior/'
    'Magic Cap Support/Interfaces')

PROFILES = {
    'cw7': CW7,
    '1.0': CW8 / 'Only 1.0',
    '1.5': CW8 / 'Only 1.5',
    'universal': CW8 / 'Universal',
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
    """Header roots, supporting both CW7's nested tree and CW8's flat tree."""
    interfaces = Path(interfaces)
    candidates = [interfaces, interfaces / 'NoDebug',
                  interfaces / 'Device/Universal/NoDebug']
    # CW8 keeps the generated system-interface headers beside the profile,
    # under the selected precompiled system-class environment.
    if interfaces.parent.name == 'Interfaces':
        candidates.append(
            interfaces.parent.parent / 'Precompiled System Classes'
            / 'Any Communicator/NoDebug/SystemInterfaces')
    return tuple(path for path in candidates if path.is_dir())
