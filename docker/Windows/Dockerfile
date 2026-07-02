FROM mcr.microsoft.com/windows/servercore:ltsc2025

SHELL ["cmd", "/S", "/C"]

ENV PYTHON_VERSION=3.10.0
ENV GIT_VERSION=2.46.0

RUN powershell -Command \
    $ProgressPreference = 'SilentlyContinue'; \
    Invoke-WebRequest \
      -Uri $('https://www.python.org/ftp/python/' + $env:PYTHON_VERSION + '/python-' + $env:PYTHON_VERSION + '-amd64.exe') \
      -OutFile C:\python-installer.exe; \
    Start-Process -Wait C:\python-installer.exe \
      -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1'; \
    Remove-Item C:\python-installer.exe
RUN copy /Y "C:\Program Files\Python310\python.exe" "C:\Program Files\Python310\python3.exe"

RUN powershell -Command \
    $ProgressPreference = 'SilentlyContinue'; \
    Invoke-WebRequest \
      -Uri $('https://github.com/git-for-windows/git/releases/download/v' + $env:GIT_VERSION + '.windows.1/Git-' + $env:GIT_VERSION + '-64-bit.exe') \
      -OutFile C:\git-installer.exe; \
    Start-Process -Wait C:\git-installer.exe -ArgumentList '/VERYSILENT /NORESTART /SP-'; \
    Remove-Item C:\git-installer.exe

RUN git config --global --add safe.directory "*"
RUN python -m pip install --no-cache-dir requests==2.31.0
RUN python -c "import certifi, shutil; shutil.copyfile(certifi.where(), r'C:\cacert.pem')"
ENV SSL_CERT_FILE=C:/cacert.pem

# https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-history#release-dates-and-build-numbers
# Build Tools 18.1.1 - December 16, 2025 - 11312.151
RUN powershell -Command \
    $ProgressPreference = 'SilentlyContinue'; \
    Invoke-WebRequest \
      -Uri https://download.visualstudio.microsoft.com/download/pr/6efb3484-905b-485c-8b5f-9d3a5f39e731/8a34e46d7ca2d21f2f3120da1fba7e9ec025732dda7d6eb4c7468b94674ae6c1/vs_BuildTools.exe \
      -OutFile C:\vs_buildtools.exe; \
    Start-Process -Wait C:\vs_buildtools.exe -ArgumentList \
      '--quiet --wait --norestart --nocache', \
      '--add Microsoft.VisualStudio.Workload.VCTools', \
      '--add Microsoft.VisualStudio.Component.VC.Tools.x86.x64', \
      '--add Microsoft.VisualStudio.Component.Windows11SDK.26100'; \
    Remove-Item C:\vs_buildtools.exe

RUN powershell -Command \
    $ProgressPreference = 'SilentlyContinue'; \
    Invoke-WebRequest \
      -Uri https://go.microsoft.com/fwlink/?linkid=2317808 \
      -OutFile C:\winsdksetup.exe; \
    Start-Process -Wait C:\winsdksetup.exe -ArgumentList \
      '/features OptionId.WindowsDesktopDebuggers /quiet /norestart'; \
    Remove-Item C:\winsdksetup.exe

WORKDIR C:/workspace
CMD ["cmd.exe"]
