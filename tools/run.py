
import os
import argparse
import sys
from typing import List

from tools.v8 import V8
from tools.types import PlatformType, ArchType, BuildConfig 

if sys.version_info < (3, 6):
    print("Error: Python 3.6 or newer is required.")
    exit()

def parseArgs():
    argParser = argparse.ArgumentParser(description='V8 Packager', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    argParser.add_argument('--fetch',
                            action='store_true',
                            help='Fetch V8')
    argParser.add_argument('--build',
                            action='store_true',
                            help='Build V8')
    argParser.add_argument('--reset',
                            action='store_true',
                            help='Reset and repatch the existing V8 checkout')
    argParser.add_argument('--archive',
                            action='store_true',
                            help='Archive V8')

    # Fetch Args
    argParser.add_argument('--version',
        type=str,
        default="13.6",
        help='Target platforms')

    # Build Args
    argParser.add_argument('--platform',
        dest='PLATFORMS',
        nargs='+',
        choices=[PlatformType.Windows.value, PlatformType.Linux.value, PlatformType.Android.value],
        default=[PlatformType.Windows.value, PlatformType.Linux.value, PlatformType.Android.value],
        help='Target platforms')
    argParser.add_argument('--arch',
        dest='ARCHITECTURES',
        nargs='+',
        choices=[ArchType.x64.value, ArchType.Arm64.value],
        default=[ArchType.x64.value, ArchType.Arm64.value],
        help='Target architecture')
    argParser.add_argument('--config',
        dest='CONFIGURATIONS',
        nargs='+',
        choices=[BuildConfig.Debug.value, BuildConfig.Release.value],
        default=[BuildConfig.Debug.value, BuildConfig.Release.value],
        help='Target configurations')
    argParser.add_argument('--library-type',
        choices=[libraryType.value for libraryType in V8.LibraryType],
        default=V8.LibraryType.Static.value,
        help='Library output type')
    
    return argParser.parse_args()


def getBuildSettingsFromArgs(args) -> List[V8.BuildSettings]:
    buildSettingsList: List[V8.BuildSettings] = []
    for platform in args.PLATFORMS:
        for arch in args.ARCHITECTURES:
            for buildConfig in args.CONFIGURATIONS:
                buildSettingsList.append(
                    V8.BuildSettings(PlatformType[platform], ArchType[arch], BuildConfig[buildConfig])
                )

    return buildSettingsList

# =============== Main ======================

def main():
    buildDir = os.path.join(os.getcwd(), 'dist')
    archiveDir = os.path.join(os.getcwd(), 'archive')

    args = parseArgs()
    if not args.fetch and not args.reset and not args.build and not args.archive:
        print("Error: Expected to have an action to run.")
        return 1

    if args.fetch:
        version = V8.Version.fromString(args.version)
        v8 = V8.initializeRepository(version)
        requestedPlatforms = [PlatformType[platform] for platform in args.PLATFORMS]
        v8.fetchBinaryDependencies(requestedPlatforms)
        v8.fetchProjectDependencies(requestedPlatforms)
        v8.applyPatches()
    if args.reset:
        v8 = V8(os.getcwd())
        v8.resetRepository()
        requestedPlatforms = [PlatformType[platform] for platform in args.PLATFORMS]
        v8.fetchBinaryDependencies(requestedPlatforms)
        v8.applyPatches()
    if args.build:
        buildSettingsList = getBuildSettingsFromArgs(args)
        if not buildSettingsList:
            print("Error: Unable to find build settings for the project.")
            return 1

        v8 = V8(os.getcwd())
        libraryType = V8.LibraryType(args.library_type)
        v8.build(buildDir, V8.ProjectSettings(libraryType), buildSettingsList)
    if args.archive:
        v8 = V8(os.getcwd())
        v8.archive(archiveDir, buildDir)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"Error: {error}")
        sys.exit(1)
