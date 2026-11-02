#Requires -Version 7.0
[CmdletBinding()]
param([string]$PythonPath, [switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$previousPath = $env:PATH
Push-Location $PluginProjectRoot
try {
    $pnpm = Initialize-FrontendTools
    $python = Get-DevelopmentPython -PythonPath $PythonPath -Create
    if (-not $SkipInstall) {
        Invoke-Checked -File $pnpm -Arguments @('install', '--frozen-lockfile')
        Invoke-Checked -File $python -Arguments @('-I', '-B', '-m', 'pip', '--disable-pip-version-check', 'install', '--only-binary=:all:', '--no-compile', '-r', (Join-Path $PluginProjectRoot 'requirements.txt'))
    }
    Invoke-Checked -File $pnpm -Arguments @('run', 'typecheck')
    Invoke-Checked -File $pnpm -Arguments @('run', 'test:frontend')
    Invoke-Checked -File $pnpm -Arguments @('run', 'build')
    Invoke-Checked -File $python -Arguments @('-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    Invoke-Checked -File $python -Arguments @('-B', '-m', 'unittest', 'discover', '-s', 'scripts/tests', '-p', 'test_*.py')
    Write-Host 'Build, typecheck y pruebas locales completados. No se ha desplegado el plugin.'
} finally {
    Pop-Location
    $env:PATH = $previousPath
}
