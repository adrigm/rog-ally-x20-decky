#Requires -Version 7.0
# Helpers compartidos. No modifica el PATH persistente ni instala herramientas.
$PluginId = 'ally-system-control'
$PluginProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Assert-SafeChildPath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Parent)
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $fullParent = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $prefix = $fullParent + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del directorio permitido: $fullPath (base: $fullParent)."
    }
    $cursor = $fullPath
    while ($cursor -and $cursor.Length -ge $fullParent.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Se rechaza una ruta con enlace simbolico o junction: $cursor."
            }
        }
        $cursor = Split-Path -Path $cursor -Parent
    }
    return $fullPath
}

function Assert-NoLinkedFiles {
    param([Parameter(Mandatory)][string]$Path)
    $linked = @(Get-ChildItem -LiteralPath $Path -Force -Recurse | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    })
    if ($linked.Count) { throw "No se admiten enlaces simbolicos/junctions en el paquete: $($linked[0].FullName)." }
}

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$File, [string[]]$Arguments = @())
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fallo el comando '$File $($Arguments -join ' ')' (codigo $LASTEXITCODE)." }
}

function Get-ToolPath {
    param([Parameter(Mandatory)][string]$Name, [string[]]$Fallback = @())
    $commands = @(Get-Command "$Name.exe", "$Name.cmd" -ErrorAction SilentlyContinue)
    if ($commands.Count) { return $commands[0].Source }
    foreach ($candidate in $Fallback) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    throw "No se encuentra $Name. Instala la herramienta o abre una terminal nueva para actualizar PATH."
}

function Initialize-FrontendTools {
    $node = Get-ToolPath -Name node -Fallback @('C:\Program Files\nodejs\node.exe')
    $pnpm = Get-ToolPath -Name pnpm -Fallback @("$env:APPDATA\npm\pnpm.cmd")
    # Solo afecta al proceso actual y sus hijos; los scripts consumidores lo restauran.
    $env:PATH = (Split-Path $node -Parent) + [IO.Path]::PathSeparator + (Split-Path $pnpm -Parent) + [IO.Path]::PathSeparator + $env:PATH
    $pnpmVersion = (& $pnpm --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pnpmVersion -notmatch '^9\.') {
        throw "Se requiere pnpm 9 por compatibilidad con la plantilla Decky (detectado: $pnpmVersion)."
    }
    return $pnpm
}

function Test-CompatiblePython {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $probe = & $Path -I -B -c 'import json, platform, struct, sys; print(json.dumps({"ok": platform.python_implementation() == "CPython" and struct.calcsize("P") == 8 and (3, 10) <= sys.version_info[:2] < (3, 15)}))' 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        return [bool](($probe | ConvertFrom-Json).ok)
    } catch { return $false }
}

function Find-CompatiblePython {
    param([string]$PythonPath)
    if ($PythonPath) {
        $explicitPath = [IO.Path]::GetFullPath($PythonPath)
        if (-not (Test-CompatiblePython -Path $explicitPath)) {
            throw "PythonPath debe apuntar a CPython x64 >=3.10 y <3.15: $explicitPath."
        }
        return $explicitPath
    }
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($command in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        if ($command.Source -notlike '*\Microsoft\WindowsApps\*') { $candidates.Add($command.Source) }
    }
    foreach ($pattern in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe", 'C:\Program Files\Python3*\python.exe')) {
        foreach ($candidate in @(Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) {
            $candidates.Add($candidate.FullName)
        }
    }
    foreach ($key in @(Get-Item -Path 'HKCU:\Software\Python\PythonCore\*\InstallPath', 'HKLM:\Software\Python\PythonCore\*\InstallPath' -ErrorAction SilentlyContinue)) {
        $candidate = $key.GetValue('ExecutablePath')
        if (-not $candidate -and $key.GetValue('')) { $candidate = Join-Path $key.GetValue('') 'python.exe' }
        if ($candidate) { $candidates.Add($candidate) }
    }
    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (Test-CompatiblePython -Path $candidate) { return $candidate }
    }
    throw 'No se encuentra CPython x64 >=3.10 y <3.15. Instala Python 3.14 en paralelo o usa -PythonPath. Python 3.15 no reproduce el runtime actual de Decky.'
}

function Get-DevelopmentPython {
    param([string]$PythonPath, [switch]$Create)
    $venvDirectory = Assert-SafeChildPath -Path (Join-Path $PluginProjectRoot '.venv') -Parent $PluginProjectRoot
    $venvPython = Join-Path $venvDirectory 'Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        if (-not (Test-CompatiblePython -Path $venvPython)) { throw 'La .venv existente no usa CPython x64 3.10–3.14. Crea un entorno compatible antes de continuar.' }
        if ($PythonPath) { $null = Find-CompatiblePython -PythonPath $PythonPath }
        return $venvPython
    }
    $basePython = Find-CompatiblePython -PythonPath $PythonPath
    if (-not $Create) { return $basePython }
    Invoke-Checked -File $basePython -Arguments @('-I', '-B', '-m', 'venv', $venvDirectory)
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "No se ha creado el entorno: $venvDirectory." }
    return $venvPython
}

function Assert-PluginStaging {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "No existe el staging: $Path. Ejecuta package.ps1 primero." }
    Assert-NoLinkedFiles -Path $Path
    foreach ($required in @('plugin.json', 'package.json', 'main.py', 'dist\index.js', 'py_modules\ally_system_control\__init__.py', 'py_modules\comtypes\__init__.py', 'LICENSE')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $required) -PathType Leaf)) { throw "Falta $required en $Path." }
    }
    $vendorMetadata = @(Get-ChildItem -LiteralPath (Join-Path $Path 'py_modules') -Directory -Filter 'comtypes-*.dist-info')
    if ($vendorMetadata.Count -ne 1) { throw 'El staging debe contener exactamente un directorio comtypes-*.dist-info con su licencia.' }
    $vendorLicenses = @(Get-ChildItem -LiteralPath $vendorMetadata[0].FullName -File -Recurse | Where-Object { $_.Name -match '^LICEN[CS]E(?:\.|$)' -and $_.Length -gt 0 })
    if (-not $vendorLicenses.Count) { throw 'Falta la licencia de comtypes en el staging. Ejecuta package.ps1 para obtener un paquete completo.' }
    $manifest = Get-Content -LiteralPath (Join-Path $Path 'package.json') -Raw | ConvertFrom-Json
    if ($manifest.name -ne $PluginId) { throw "El paquete debe identificarse como $PluginId; detectado: $($manifest.name)." }
}
