# Install the Tringify theme tools on Windows.
#
#   irm https://raw.githubusercontent.com/tringify/theme-tools/main/install.ps1 | iex
#
# Environment:
#   TRINGIFY_THEME_TOOLS_VERSION  release tag to install (default: latest)
#   TRINGIFY_THEME_TOOLS_HOME     installation directory (default: %LOCALAPPDATA%\Tringify\theme-tools)
$ErrorActionPreference = 'Stop'

$repo = 'tringify/theme-tools'
$version = if ($env:TRINGIFY_THEME_TOOLS_VERSION) { $env:TRINGIFY_THEME_TOOLS_VERSION } else { 'latest' }
$homeDir = if ($env:TRINGIFY_THEME_TOOLS_HOME) { $env:TRINGIFY_THEME_TOOLS_HOME } else { Join-Path $env:LOCALAPPDATA 'Tringify\theme-tools' }

if ([System.Environment]::Is64BitOperatingSystem -eq $false) { throw 'A 64-bit version of Windows is required.' }
$python = $null
foreach ($candidate in @(@('py', '-3'), @('python'))) {
  $exe = Get-Command $candidate[0] -ErrorAction SilentlyContinue
  if ($exe) {
    $pyArgs = @($candidate | Select-Object -Skip 1) + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)')
    & $exe.Source @pyArgs 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
  }
}
if (-not $python) { throw 'Python 3.10 or newer is required.' }

$base = if ($version -eq 'latest') { "https://github.com/$repo/releases/latest/download" } else { "https://github.com/$repo/releases/download/$version" }
$archive = 'tringify-theme-tools-windows-amd64.zip'
$work = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $work | Out-Null
try {
  Write-Host "Downloading $archive ($version)"
  Invoke-WebRequest -UseBasicParsing -Uri "$base/$archive" -OutFile (Join-Path $work $archive)
  Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS" -OutFile (Join-Path $work 'SHA256SUMS')
  $line = Get-Content (Join-Path $work 'SHA256SUMS') | Where-Object { ($_ -split '\s+')[1] -in @($archive, "*$archive") } | Select-Object -First 1
  if (-not $line) { throw "No checksum published for $archive." }
  $expected = ($line -split '\s+')[0].ToLowerInvariant()
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $work $archive)).Hash.ToLowerInvariant()
  if ($expected -ne $actual) { throw "Checksum mismatch for $archive." }

  Expand-Archive -Path (Join-Path $work $archive) -DestinationPath (Join-Path $work 'extract')
  $source = Join-Path $work 'extract\tringify-theme-tools'
  if (-not (Test-Path (Join-Path $source 'theme.py'))) { throw 'Unexpected archive layout.' }
  if (Test-Path $homeDir) { Remove-Item -Recurse -Force $homeDir }
  New-Item -ItemType Directory -Path (Split-Path $homeDir) -Force | Out-Null
  Move-Item $source $homeDir
} finally {
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (($userPath -split ';') -contains $homeDir)) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $homeDir).TrimStart(';'), 'User')
  Write-Host "Added $homeDir to your user PATH. Open a new terminal before running tringify-theme."
}
Write-Host "Installed to $homeDir. Run: tringify-theme --help"
