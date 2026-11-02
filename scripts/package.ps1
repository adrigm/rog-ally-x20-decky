#Requires -Version 7.0
[CmdletBinding()]
param([string]$PythonPath, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Push-Location $PluginProjectRoot
try {
    if (-not $SkipBuild) { & (Join-Path $PSScriptRoot 'build.ps1') -PythonPath $PythonPath }
    $python = Get-DevelopmentPython -PythonPath $PythonPath -Create
    $stagingParent = Assert-SafeChildPath -Path (Join-Path $PluginProjectRoot 'out\staging') -Parent $PluginProjectRoot
    $staging = Assert-SafeChildPath -Path (Join-Path $stagingParent $PluginId) -Parent $stagingParent
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    $null = New-Item -Path $staging -ItemType Directory -Force
    foreach ($file in @('plugin.json', 'package.json', 'main.py', 'LICENSE', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $PluginProjectRoot $file) -Destination (Join-Path $staging $file)
    }
    $null = New-Item -Path (Join-Path $staging 'dist') -ItemType Directory
    Copy-Item -LiteralPath (Join-Path $PluginProjectRoot 'dist\index.js') -Destination (Join-Path $staging 'dist\index.js')
    $moduleDestination = Join-Path $staging 'py_modules'
    $null = New-Item -Path $moduleDestination -ItemType Directory
    $moduleSource = Join-Path $PluginProjectRoot 'py_modules\ally_system_control'
    Assert-NoLinkedFiles -Path $moduleSource
    Copy-Item -LiteralPath $moduleSource -Destination $moduleDestination -Recurse
    # Pip solo escribe en staging. No modifica Python global ni descarga fuentes nativas.
    Invoke-Checked -File $python -Arguments @('-I', '-B', '-m', 'pip', '--disable-pip-version-check', 'install', '--only-binary=:all:', '--no-compile', '--target', $moduleDestination, '-r', (Join-Path $PluginProjectRoot 'requirements.txt'))
    $generatedDirectories = @(Get-ChildItem -LiteralPath $staging -Directory -Recurse -Force | Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') } | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $generatedDirectories) {
        $safeDirectory = Assert-SafeChildPath -Path $directory.FullName -Parent $staging
        Remove-Item -LiteralPath $safeDirectory -Recurse -Force
    }
    foreach ($file in @(Get-ChildItem -LiteralPath $staging -File -Recurse -Force | Where-Object { $_.Extension -in @('.pyc', '.pyo') })) {
        $safeFile = Assert-SafeChildPath -Path $file.FullName -Parent $staging
        Remove-Item -LiteralPath $safeFile -Force
    }
    Assert-PluginStaging -Path $staging
    $manifest = Get-Content -LiteralPath (Join-Path $staging 'package.json') -Raw | ConvertFrom-Json
    if ($manifest.version -notmatch '^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') { throw 'La version del paquete no es valida.' }
    $artifacts = Assert-SafeChildPath -Path (Join-Path $PluginProjectRoot 'artifacts') -Parent $PluginProjectRoot
    $null = New-Item -Path $artifacts -ItemType Directory -Force
    $archive = Assert-SafeChildPath -Path (Join-Path $artifacts "$PluginId-$($manifest.version).zip") -Parent $artifacts
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -LiteralPath $staging -DestinationPath $archive -CompressionLevel Optimal
    Invoke-Checked -File $python -Arguments @('-I', '-B', (Join-Path $PSScriptRoot 'verify-package.py'), $archive)
    $hash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
    [IO.File]::WriteAllText("$archive.sha256", "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($archive))`n", [Text.UTF8Encoding]::new($false))
    Write-Host "ZIP verificado: $archive"
    Write-Host "Staging para revision/despliegue: $staging"
} finally { Pop-Location }
