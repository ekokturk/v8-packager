# V8 Library Packager

A tool to compile and package [V8 JavaScript Engine](https://v8.dev/) libraries.

### Dependencies
- Python 3.6+

### How to use
- Fetch the V8 repository:
    ```
    python3 run.py --fetch --version <"11.1">
    ```
- Compile libraries and output build dependencies:
    ```
    python3 run.py --build --platform <windows|linux|android> --arch <x64|arm64> --config <Release|Debug>
    ```
- Archive libraries for each platform:
    ```
    python3 run.py --archive
    ```

- Run `BuildAll.bat` to generate libraries for all available platforms on Windows with WSL.