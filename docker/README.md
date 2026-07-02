# Docker builds

```bat
BuildAll_DockerDesktop.bat
BuildAll_DockerDesktop.bat 13.6 Static
BuildAll_DockerDesktop.bat 13.6 Shared
```

```sh
python docker/docker.py --image linux
python docker/docker.py --image windows
```

```sh
python docker/docker.py --build windows --arch x64 --config Debug --library-type Static
python docker/docker.py --build windows --arch x64 --config Debug Release --library-type Shared
python docker/docker.py --build linux --arch x64 --config Release --library-type Static
python docker/docker.py --build android --arch Arm64 --config Release --library-type Static
```

```sh
python docker/docker.py --build windows --archive
python docker/docker.py --build linux --config Debug Release --archive
python docker/docker.py --build android --arch x64 Arm64 --config Debug Release --archive
```

```sh
python docker/docker.py --build linux --memory 16g --jobs 8
python docker/docker.py --build android --version 13.6 --library-type Shared --archive
```
