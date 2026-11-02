#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$HomebrewPath = (Join-Path $env:USERPROFILE 'homebrew'),
    [string]$StagingPath,
    [string]$RestoreBackupPath
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
if ($StagingPath -and $RestoreBackupPath) { throw 'Usa StagingPath o RestoreBackupPath, no ambos.' }
$homebrew = [IO.Path]::GetFullPath($HomebrewPath).TrimEnd([IO.Path]::DirectorySeparatorChar)
if (-not (Test-Path -LiteralPath $homebrew -PathType Container)) { throw "No existe HomebrewPath: $homebrew. Indica la carpeta de Decky existente." }
$pluginsDirectory = Assert-SafeChildPath -Path (Join-Path $homebrew 'plugins') -Parent $homebrew
if (-not (Test-Path -LiteralPath $pluginsDirectory -PathType Container)) { throw "No existe la carpeta plugins de Decky: $pluginsDirectory." }
$destination = Assert-SafeChildPath -Path (Join-Path $pluginsDirectory $PluginId) -Parent $pluginsDirectory
$backupRoot = Assert-SafeChildPath -Path (Join-Path $homebrew "backups\$PluginId") -Parent $homebrew
$stagingRoot = Assert-SafeChildPath -Path (Join-Path $PluginProjectRoot 'out\staging') -Parent $PluginProjectRoot
if ($RestoreBackupPath) {
    $source = Assert-SafeChildPath -Path $RestoreBackupPath -Parent $backupRoot
} elseif ($StagingPath) {
    $source = Assert-SafeChildPath -Path $StagingPath -Parent $stagingRoot
} else {
    $source = Assert-SafeChildPath -Path (Join-Path $stagingRoot $PluginId) -Parent $stagingRoot
}
Assert-PluginStaging -Path $source
$deploymentId = [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$workingCopy = Assert-SafeChildPath -Path (Join-Path $homebrew ".ally-system-control-deploy-$deploymentId") -Parent $homebrew
$backup = Assert-SafeChildPath -Path (Join-Path $backupRoot $deploymentId) -Parent $backupRoot
$oldMoved = $false
$newInstalled = $false
try {
    # Primero preparar una copia completa fuera de plugins, antes de tocar la copia actual.
    $null = New-Item -Path $workingCopy -ItemType Directory
    foreach ($item in @(Get-ChildItem -LiteralPath $source -Force)) {
        Copy-Item -LiteralPath $item.FullName -Destination $workingCopy -Recurse
    }
    Assert-PluginStaging -Path $workingCopy
    if (Test-Path -LiteralPath $destination) {
        $null = New-Item -Path $backupRoot -ItemType Directory -Force
        $safeDestination = Assert-SafeChildPath -Path $destination -Parent $pluginsDirectory
        $safeBackup = Assert-SafeChildPath -Path $backup -Parent $backupRoot
        Move-Item -LiteralPath $safeDestination -Destination $safeBackup
        $oldMoved = $true
    }
    $safeWorkingCopy = Assert-SafeChildPath -Path $workingCopy -Parent $homebrew
    $safeDestination = Assert-SafeChildPath -Path $destination -Parent $pluginsDirectory
    Move-Item -LiteralPath $safeWorkingCopy -Destination $safeDestination
    $newInstalled = $true
    Write-Host "Plugin copiado en: $destination"
    if ($oldMoved) {
        Write-Host "Copia anterior: $backup"
        Write-Host "Para restaurarla: ./scripts/deploy-dev.ps1 -HomebrewPath '$homebrew' -RestoreBackupPath '$backup'"
    } else { Write-Host 'Primera instalacion: no existia una copia anterior.' }
    Write-Host 'Steam, Decky y los demas plugins no se han reiniciado.'
} catch {
    $deploymentError = $_
    if ($oldMoved -and -not $newInstalled -and -not (Test-Path -LiteralPath $destination)) {
        try {
            $safeBackup = Assert-SafeChildPath -Path $backup -Parent $backupRoot
            $safeDestination = Assert-SafeChildPath -Path $destination -Parent $pluginsDirectory
            Move-Item -LiteralPath $safeBackup -Destination $safeDestination
            Write-Warning 'Se ha restaurado automaticamente la copia anterior tras el fallo.'
        } catch { Write-Warning "No se pudo restaurar automaticamente. La copia sigue en $backup. Error: $($_.Exception.Message)" }
    }
    throw "No se ha completado el despliegue: $($deploymentError.Exception.Message). Si Windows indica acceso denegado, revisa permisos o archivos abiertos de esta carpeta. El script no eleva permisos ni termina procesos."
} finally {
    if (Test-Path -LiteralPath $workingCopy) {
        $safeWorkingCopy = Assert-SafeChildPath -Path $workingCopy -Parent $homebrew
        Remove-Item -LiteralPath $safeWorkingCopy -Recurse -Force
    }
}
