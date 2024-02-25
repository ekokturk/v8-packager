
import os
import subprocess
import argparse
from typing import List

from utils.v8 import V8
from utils.types import PlatformType, ArchType, BuildConfig 

try:
    # python3 is required for build scripts
    subprocess.run('python3 --version', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
except subprocess.CalledProcessError as e:
    print("Error: python3 does not exist on your system.")
    exit()

def parseArgs():
    argParser = argparse.ArgumentParser(description='V8 Packager', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    argParser.add_argument('--fetch',
                            action='store_true',
                            help='Fetch V8')
    argParser.add_argument('--build',
                            action='store_true',
                            help='Build V8')
    argParser.add_argument('--archive',
                            action='store_true',
                            help='Archive V8')

    # Fetch Args
    argParser.add_argument('--version',
        type=str,
        default="11.1",
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
    
    return argParser.parse_args()


def getBuildSettingsFromArgs(args):
    list: List[V8.BuildSettings] = []
    for platform in args.PLATFORMS:
        for arch in args.ARCHITECTURES:
            for buildConfig in args.CONFIGURATIONS:
                try:
                    list.append(V8.BuildSettings(PlatformType[platform], ArchType[arch], BuildConfig[buildConfig]))
                except subprocess.CalledProcessError as e:
                    print("Error: Unable to parse command line arguments.")
                    return
                
    return list

# =============== Main ======================

buildDir = os.path.join(os.getcwd(), 'dist')
archiveDir = os.path.join(os.getcwd(), 'archive')

args = parseArgs()
if args.fetch:
    version = V8.Version.fromString(args.version)
    v8 = V8.initializeRepository(version)
    v8.fetchBinaryDependencies()
    v8.fetchProjectDependencies()
    v8.applyPatches()
if args.build:
    buildSettingsList = getBuildSettingsFromArgs(args)
    if buildSettingsList == []:
        print("Error: Unable to find build settings for the project.")
    else:
        v8 = V8(os.getcwd())
        v8.build(buildDir, V8.ProjectSettings(), buildSettingsList)
if args.archive:
    v8 = V8(os.getcwd())
    v8.archive(archiveDir, buildDir)

if not args.fetch and not args.build and not args.archive:
    print("Error: Expected to have an action to run.")