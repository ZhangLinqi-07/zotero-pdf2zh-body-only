@echo off
setlocal
chcp 65001 >nul
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" goto unsupported
if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" goto unsupported
set "BODY_BOOT=%~dp0.bootstrap"
set "BODY_UV_ARCHIVE=%BODY_BOOT%\uv-0.13.4.zip"
if not exist "%BODY_BOOT%" mkdir "%BODY_BOOT%"
if not exist "%BODY_UV_ARCHIVE%" (
  echo Downloading the pinned uv bootstrap tool ...
  curl.exe --fail --location --retry 2 --connect-timeout 15 --max-time 180 --output "%BODY_UV_ARCHIVE%.part" "https://releases.astral.sh/github/uv/releases/download/0.13.4/uv-x86_64-pc-windows-msvc.zip"
  if errorlevel 1 goto failed
  move /y "%BODY_UV_ARCHIVE%.part" "%BODY_UV_ARCHIVE%" >nul
)
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $stream=[IO.File]::OpenRead($env:BODY_UV_ARCHIVE); try { $hash=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($stream)).Replace('-','').ToLowerInvariant() } finally { $stream.Dispose() }; if ($hash -ne 'ccec7508a07d9933d7cb1261880633efcf1f30d6e6eddab21823f1dae6f23225') { throw 'uv download checksum mismatch. Delete .bootstrap/uv-0.13.4.zip and try again.' }; [void][Reflection.Assembly]::LoadWithPartialName('System.IO.Compression.FileSystem'); [void][IO.Directory]::CreateDirectory($env:BODY_BOOT + '/bin'); $zip=[IO.Compression.ZipFile]::OpenRead($env:BODY_UV_ARCHIVE); try { [IO.Compression.ZipFileExtensions]::ExtractToFile($zip.GetEntry('uv.exe'), $env:BODY_BOOT + '/bin/uv.exe', $true) } finally { $zip.Dispose() }"
if errorlevel 1 goto failed
set "UV_PYTHON_INSTALL_DIR=%BODY_BOOT%\python"
set "UV_PYTHON_BIN_DIR=%BODY_BOOT%\python-bin"
"%BODY_BOOT%\bin\uv.exe" python install 3.12 --no-bin --no-registry
if errorlevel 1 goto failed
"%BODY_BOOT%\bin\uv.exe" run --no-project --no-config --python 3.12 python "%~dp0setup_fresh.py" --uv "%BODY_BOOT%\bin\uv.exe" --start %*
if errorlevel 1 goto failed
exit /b 0
:unsupported
echo This launcher supports Windows x64. Other systems can use setup_fresh.py with Python and uv.
pause
exit /b 1
:failed
echo Installation stopped. Read the error above. Rerun this file to resume.
pause
exit /b 1
