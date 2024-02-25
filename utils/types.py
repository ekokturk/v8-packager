from enum import Enum
from typing import Dict

class PlatformType(Enum):
    Windows = "Windows"
    Linux = "Linux"
    Android = "Android"

class ArchType(Enum):
    x64 = "x64"
    Arm64 = "Arm64"

class BuildConfig(Enum):
    Debug = "Debug"
    Release = "Release"

EnvVars = Dict[str, str]