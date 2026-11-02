#Requires -Version 7.0
<# Solo lectura: consulta capacidades/estado Windows desde el staging distribuible.
   No modifica volumen, mute ni brillo. No instala ni despliega archivos. #>
[CmdletBinding()]
param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$python = Get-DevelopmentPython -PythonPath $PythonPath
$staging = Assert-SafeChildPath -Path (Join-Path $PluginProjectRoot "out\staging\$PluginId") -Parent (Join-Path $PluginProjectRoot 'out\staging')
Assert-PluginStaging -Path $staging
$probe = 'import pathlib, runpy, sys; plugin = pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0, str(plugin / "py_modules")); sys.argv = ["ally_system_control.probe", "--read-only"]; runpy.run_module("ally_system_control.probe", run_name="__main__")'
Invoke-Checked -File $python -Arguments @('-I', '-B', '-c', $probe, $staging)
