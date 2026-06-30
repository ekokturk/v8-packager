# V8 Library Packager

A tool to compile and package [V8 JavaScript Engine](https://v8.dev/) libraries.

### Dependencies
- Python 3.6+

### How to use
- Fetch the V8 repository:
    ```
    python3 -m tools.run --fetch --version <"13.6">
    ```
- Compile libraries and output build dependencies:
    ```
    python3 -m tools.run --build --platform <windows|linux|android> --arch <x64|arm64> --config <Release|Debug> --library-type <Shared|Static>
    ```

- Build a single static library for Windows x64 Debug:
    ```
    python3 -m tools.run --build --platform Windows --arch x64 --config Debug --library-type Static
    ```
- Archive libraries for each platform:
    ```
    python3 -m tools.run --archive
    ```
- Run `BuildAll_DockerDesktop.bat` to generate and archive Windows, Linux, and
  Android libraries using isolated Docker workspaces.
