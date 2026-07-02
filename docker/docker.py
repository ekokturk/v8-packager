import argparse
import os
import shutil
import subprocess
import time
from enum import Enum


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
IMAGE_PREFIX = "v8-packager"


class Platform(str, Enum):
    Windows = "windows"
    Linux = "linux"
    Android = "android"


SUPPORTED_ARCHITECTURES = {
    Platform.Windows: ["x64"],
    Platform.Linux: ["x64"],
    Platform.Android: ["x64", "Arm64"],
}
BUILD_CONFIGURATIONS = ["Debug", "Release"]
IMAGE_PLATFORMS = [Platform.Windows, Platform.Linux]


def docker_platform(platform):
    if platform == Platform.Android:
        return Platform.Linux
    return platform


def run(command):
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def docker_os(timeout=180):
    deadline = time.monotonic() + timeout
    last_error = ""
    while True:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            try:
                return Platform(value)
            except ValueError:
                last_error = f"Docker returned an unknown OS type: {value!r}"
        else:
            last_error = (result.stderr or result.stdout).strip()

        if time.monotonic() >= deadline:
            detail = f": {last_error}" if last_error else ""
            raise RuntimeError(
                f"Docker did not become ready within {timeout} seconds{detail}"
            )
        time.sleep(2)


def image_name(platform):
    platform = docker_platform(platform)
    return f"{IMAGE_PREFIX}/{platform.value}:latest"


def build_image(platform):
    platform = docker_platform(platform)
    run([
        "docker",
        "build",
        "--tag",
        image_name(platform),
        os.path.join(SCRIPT_DIR, platform.name),
    ])


def build_v8(
    platform, source, workspace, architectures, configurations, library_type,
    memory, jobs, prepare, git_cache,
    archive_dir=None, version="13.6"
):
    required_os = docker_platform(platform)
    active_os = docker_os()
    if active_os != required_os:
        raise RuntimeError(
            f"Docker is running {active_os.value} containers; "
            f"switch Docker to {required_os.value} containers first."
        )

    container_workspace = (
        "C:/workspace" if required_os == Platform.Windows else "/workspace"
    )
    command = [
        "python" if required_os == Platform.Windows else "python3",
        "-m",
        "tools.run",
    ]
    if prepare == "fetch":
        command.extend(["--fetch", "--version", version])
    elif prepare == "reset":
        command.append("--reset")
    command.extend(["--build", "--platform", platform.name, "--arch"])
    command.extend(architectures)
    command.append("--config")
    command.extend(configurations)
    command.extend(["--library-type", library_type])
    if archive_dir:
        command.append("--archive")
    volumes = [
        (workspace, container_workspace, False),
        (git_cache, "C:/git-cache" if required_os == Platform.Windows
         else "/git-cache", False),
        (os.path.join(source, "patches"), f"{container_workspace}/patches", True),
        (os.path.join(source, "tools"), f"{container_workspace}/tools", True),
    ]
    if archive_dir:
        volumes.append(
            (archive_dir, f"{container_workspace}/archive", False)
        )
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--memory",
        memory,
    ]
    if required_os == Platform.Windows:
        docker_command.extend(["--cpu-count", "16"])
    docker_command.extend([
        "--env",
        "V8_PACKAGER_GIT_CACHE="
        + ("C:/git-cache" if required_os == Platform.Windows else "/git-cache"),
        "--env",
        "PYTHONUNBUFFERED=1",
        "--env",
        f"V8_PACKAGER_JOBS={jobs}",
    ])
    for host_path, container_path, read_only in volumes:
        volume = f"{host_path}:{container_path}"
        if read_only:
            volume += ":ro"
        docker_command.extend(["--volume", volume])
    docker_command.extend([
        "--workdir", container_workspace, image_name(platform), *command,
    ])
    run(docker_command)


def prepare_workspace(source, platform):
    source = os.path.abspath(source)
    workspace = os.path.join(source, ".docker", f"workspace-{platform.value}")
    os.makedirs(workspace, exist_ok=True)
    print(f"Using {platform.value} build workspace: {workspace}")
    return workspace


def has_valid_checkout(workspace):
    git_dir = os.path.join(workspace, "v8", ".git")
    head_file = os.path.join(git_dir, "HEAD")
    if not os.path.isfile(head_file):
        return False
    with open(head_file) as file:
        head = file.read().strip()
    if head.startswith("ref: "):
        ref = head[5:]
        if os.path.isfile(os.path.join(git_dir, *ref.split("/"))):
            return True
        packed_refs = os.path.join(git_dir, "packed-refs")
        if os.path.isfile(packed_refs):
            with open(packed_refs) as file:
                return any(
                    line.rstrip().endswith(" " + ref)
                    for line in file
                    if line and line[0] not in "#^"
                )
        return False
    return len(head) == 40 and all(char in "0123456789abcdef" for char in head.lower())


def export_artifacts(workspace, destination):
    source = os.path.join(workspace, "dist")
    if not os.path.isdir(source):
        raise RuntimeError("The temporary workspace did not produce a dist directory.")
    destination = os.path.join(destination, "dist")
    os.makedirs(destination, exist_ok=True)
    for name in os.listdir(source):
        source_path = os.path.join(source, name)
        destination_path = os.path.join(destination, name)
        if os.path.isdir(source_path):
            if os.path.isdir(destination_path):
                shutil.rmtree(destination_path)
            shutil.copytree(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
    print(f"Exported build artifacts to: {destination}")


def main():
    parser = argparse.ArgumentParser(description="Build V8 using Docker")
    parser.add_argument(
        "--image", nargs="+",
        choices=[platform.value for platform in IMAGE_PLATFORMS],
        help="Build one or more Docker images",
    )
    parser.add_argument(
        "--build", choices=[platform.value for platform in Platform],
        help="Build V8 for this platform",
    )
    parser.add_argument(
        "--workspace",
        default=PROJECT_DIR,
        help="Source repository containing patches and tools",
    )
    parser.add_argument(
        "--arch",
        nargs="+",
        choices=["x64", "Arm64"],
        help="Architectures to build; defaults to all supported by the platform",
    )
    parser.add_argument(
        "--config",
        nargs="+",
        choices=BUILD_CONFIGURATIONS,
        help="Configurations to build; defaults to Debug and Release",
    )
    parser.add_argument(
        "--library-type",
        choices=["Shared", "Static"],
        default="Static",
    )
    parser.add_argument("--memory", default="24g")
    parser.add_argument(
        "--jobs",
        type=int,
        default=16,
        help="Maximum parallel Ninja jobs",
    )
    parser.add_argument("--version", default="13.6")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Archive build outputs into the host archive directory",
    )
    args = parser.parse_args()

    if not args.image and not args.build:
        parser.error("at least one of --image or --build is required")
    if args.archive and not args.build:
        parser.error("--archive requires --build")
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    for platform in args.image or []:
        build_image(Platform(platform))
    if args.build:
        source_workspace = os.path.abspath(args.workspace)
        requested_platform = Platform(args.build)
        required_os = docker_platform(requested_platform)
        active_platform = docker_os()
        if active_platform != required_os:
            raise RuntimeError(
                f"Docker is running {active_platform.value} containers; "
                f"switch Docker to {required_os.value} containers first."
            )
        build_workspace = prepare_workspace(
            source_workspace, requested_platform
        )
        git_cache = os.path.join(source_workspace, ".docker", "git-cache")
        os.makedirs(git_cache, exist_ok=True)
        archive_dir = None
        if args.archive:
            archive_dir = os.path.join(source_workspace, "archive")
            os.makedirs(archive_dir, exist_ok=True)
        architectures = args.arch or SUPPORTED_ARCHITECTURES[requested_platform]
        configurations = args.config or BUILD_CONFIGURATIONS
        prepare = (
            "reset"
            if has_valid_checkout(build_workspace)
            else "fetch"
        )
        build_v8(
            requested_platform,
            source_workspace,
            build_workspace,
            architectures,
            configurations,
            args.library_type,
            args.memory,
            args.jobs,
            prepare=prepare,
            git_cache=git_cache,
            archive_dir=archive_dir,
            version=args.version,
        )
        export_artifacts(build_workspace, source_workspace)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Error: {error}")
        raise SystemExit(1)
