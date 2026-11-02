#Requires -Version 7.0
<#
.SYNOPSIS
  Diagnostico de solo lectura del entorno Windows para el plugin de Decky.
.DESCRIPTION
  No instala paquetes, no cambia PATH ni configuracion, no reinicia aplicaciones
  y no modifica brillo ni volumen. No abre ventanas ni prueba escrituras WMI.
  No recoge numeros de serie, lineas de comandos de procesos, tokens ni ajustes
  privados de Steam/Decky. Solo escribe un informe si se indica -OutputPath.
.EXAMPLE
  .\scripts\diagnose-environment.ps1
.EXAMPLE
  .\scripts\diagnose-environment.ps1 -OutputPath .\docs\environment-audit.json
#>
[CmdletBinding()]
param([string]$OutputPath)

$ErrorActionPreference = 'Stop'
$auditErrors = [System.Collections.Generic.List[object]]::new()

function Add-AuditError([string]$Section, [object]$Failure) {
    $auditErrors.Add([pscustomobject]@{ section = $Section; message = $Failure.Exception.Message })
}

function Get-AuditCommand([string]$Name, [string[]]$Fallback = @()) {
    $commands = @(Get-Command "$Name.exe", "$Name.cmd" -ErrorAction SilentlyContinue)
    if ($commands.Count -gt 0) { return $commands[0].Source }
    foreach ($candidate in $Fallback) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    return $null
}

function Get-AuditTool([string]$Name, [string[]]$Arguments = @('--version'), [string[]]$Fallback = @()) {
    $commandPath = Get-AuditCommand -Name $Name -Fallback $Fallback
    if (-not $commandPath) {
        return [pscustomobject]@{ available = $false; commandPath = $null; version = $null; exitCode = $null }
    }
    try {
        $versionText = (& $commandPath @Arguments 2>&1 | Out-String).Trim()
        return [pscustomobject]@{ available = $true; commandPath = $commandPath; version = $versionText; exitCode = $LASTEXITCODE }
    } catch {
        Add-AuditError -Section "tools.$Name" -Failure $_
        return [pscustomobject]@{ available = $true; commandPath = $commandPath; version = $null; exitCode = $null }
    }
}

try { $madridZone = [TimeZoneInfo]::FindSystemTimeZoneById('Europe/Madrid') }
catch { $madridZone = [TimeZoneInfo]::FindSystemTimeZoneById('Romance Standard Time') }
$utcNow = [DateTimeOffset]::UtcNow
$audit = [ordered]@{
    schemaVersion = 1
    recordedAt = [TimeZoneInfo]::ConvertTime($utcNow, $madridZone).ToString('o')
    timeZone = 'Europe/Madrid'
    scope = 'Read-only inventory; no volume or brightness writes; no UI verification.'
    os = $null
    hardware = $null
    python = $null
    tools = [ordered]@{}
    steam = $null
    decky = $null
    brightness = $null
    errors = @()
}

try {
    $os = Get-CimInstance Win32_OperatingSystem
    $audit.os = [pscustomobject]@{
        caption = $os.Caption; version = $os.Version; build = $os.BuildNumber
        architecture = $os.OSArchitecture; powershellVersion = $PSVersionTable.PSVersion.ToString()
    }
    $computer = Get-CimInstance Win32_ComputerSystem
    $bios = Get-CimInstance Win32_BIOS
    $memory = @(Get-CimInstance Win32_PhysicalMemory)
    $audit.hardware = [pscustomobject]@{
        manufacturer = $computer.Manufacturer; model = $computer.Model; systemType = $computer.SystemType
        hypervisorPresent = $computer.HypervisorPresent
        cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { $_.Name.Trim() })
        gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
        bios = [pscustomobject]@{ manufacturer = $bios.Manufacturer; version = $bios.SMBIOSBIOSVersion }
        physicalMemoryBytes = ($memory | Measure-Object Capacity -Sum).Sum
        memoryVisibleToWindowsBytes = $computer.TotalPhysicalMemory
        memoryModules = @($memory | Select-Object Capacity, Speed, ConfiguredClockSpeed)
    }
} catch { Add-AuditError -Section 'hardware' -Failure $_ }

# Skip WindowsApps launch aliases to avoid launching the Store if Python is absent.
$pythonPath = $null
$pythonCommands = @(Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\Microsoft\WindowsApps\*' })
if ($pythonCommands.Count -gt 0) { $pythonPath = $pythonCommands[0].Source }
if (-not $pythonPath) {
    $pythonCandidates = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($pythonCandidates.Count -gt 0) { $pythonPath = $pythonCandidates[0].FullName }
}
if (-not $pythonPath) {
    $pythonRegistryKeys = @(Get-Item -Path 'HKCU:\Software\Python\PythonCore\*\InstallPath', 'HKLM:\Software\Python\PythonCore\*\InstallPath' -ErrorAction SilentlyContinue)
    foreach ($registryKey in $pythonRegistryKeys) {
        $candidate = $registryKey.GetValue('ExecutablePath')
        if (-not $candidate) {
            $installDirectory = $registryKey.GetValue('')
            if ($installDirectory) { $candidate = Join-Path $installDirectory 'python.exe' }
        }
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { $pythonPath = $candidate; break }
    }
}
if ($pythonPath) {
    try {
        $pythonProbe = 'import sys, struct, platform, importlib.util, json; print(json.dumps({"available": True, "version": platform.python_version(), "fullVersion": sys.version, "executable": sys.executable, "bits": struct.calcsize("P") * 8, "implementation": platform.python_implementation(), "packages": {name: importlib.util.find_spec(name) is not None for name in ("pip", "venv", "ctypes", "comtypes", "pycaw", "win32com", "pytest")}}))'
        $pythonJson = & $pythonPath -B -c $pythonProbe
        if ($LASTEXITCODE -ne 0) { throw 'Python probe failed.' }
        $pythonInfo = $pythonJson | ConvertFrom-Json
        $pipVersion = $null
        if ($pythonInfo.packages.pip) { $pipVersion = (& $pythonPath -B -m pip --version 2>&1 | Out-String).Trim() }
        $pythonInfo | Add-Member -NotePropertyName pipVersion -NotePropertyValue $pipVersion
        $audit.python = $pythonInfo
    } catch { Add-AuditError -Section 'python' -Failure $_ }
} else {
    $audit.python = [pscustomobject]@{ available = $false; note = 'No runtime resolved; WindowsApps aliases were not executed.' }
}

$audit.tools.node = Get-AuditTool -Name node
$audit.tools.npm = Get-AuditTool -Name npm
$audit.tools.pnpm = Get-AuditTool -Name pnpm
$audit.tools.git = Get-AuditTool -Name git -Fallback @('C:\Program Files\Git\cmd\git.exe', "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")
$audit.tools.winget = Get-AuditTool -Name winget
$audit.tools.dotnet = Get-AuditTool -Name dotnet
$dotnetPath = Get-AuditCommand -Name dotnet
if ($dotnetPath) {
    try {
        $audit.tools.dotnet | Add-Member -NotePropertyName sdks -NotePropertyValue @(& $dotnetPath --list-sdks)
        $audit.tools.dotnet | Add-Member -NotePropertyName runtimes -NotePropertyValue @(& $dotnetPath --list-runtimes)
    } catch { Add-AuditError -Section 'tools.dotnet' -Failure $_ }
}

try {
    $steamRegistry = Get-ItemProperty -Path HKCU:\Software\Valve\Steam -ErrorAction SilentlyContinue
    $steamDirectory = $steamRegistry.SteamPath
    if ($steamDirectory) { $steamDirectory = $steamDirectory.Replace('/', '\') }
    $steamExecutable = if ($steamDirectory) { Join-Path $steamDirectory 'steam.exe' } else { $null }
    $steamExists = $steamExecutable -and (Test-Path -LiteralPath $steamExecutable -PathType Leaf)
    $steamVersion = if ($steamExists) { (Get-Item -LiteralPath $steamExecutable).VersionInfo.FileVersion } else { $null }
    $cefMarker = if ($steamDirectory) { Join-Path $steamDirectory '.cef-enable-remote-debugging' } else { $null }
    $audit.steam = [pscustomobject]@{
        installed = [bool]$steamExists; directory = $steamDirectory; fileVersion = $steamVersion
        cefDebuggingMarkerPresent = [bool]($cefMarker -and (Test-Path -LiteralPath $cefMarker))
        note = 'File version is not the Steam channel/build identifier; no UI was checked.'
    }
} catch { Add-AuditError -Section 'steam' -Failure $_ }

try {
    $homebrewDirectory = Join-Path $env:USERPROFILE 'homebrew'
    $pluginDirectory = Join-Path $homebrewDirectory 'plugins'
    $deckyProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'PluginLoader_noconsole.exe' OR Name = 'PluginLoader.exe' OR Name = 'PluginLoader-win.exe' OR Name = 'PluginLoader-win-noconsole.exe'" | Select-Object Name, ProcessId, ParentProcessId, ExecutablePath)
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @(1337, 8080) } | ForEach-Object {
        $listenerProcess = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{ address = $_.LocalAddress; port = $_.LocalPort; process = $listenerProcess.ProcessName }
    })
    $audit.decky = [pscustomobject]@{
        homebrewDirectory = $homebrewDirectory; homebrewDirectoryExists = Test-Path -LiteralPath $homebrewDirectory
        plugins = @(Get-ChildItem -LiteralPath $pluginDirectory -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
        processCount = $deckyProcesses.Count; processes = $deckyProcesses; listeners = $listeners
        installedVersion = $null
        note = 'Processes/ports do not prove frontend compatibility or plugin health. Multiple processes can be child workers. Version not inferred from filenames.'
    }
} catch { Add-AuditError -Section 'decky' -Failure $_ }

try {
    $brightnessInstances = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object Active, InstanceName, CurrentBrightness, Levels, Level)
    $brightnessMethods = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select-Object Active, InstanceName)
    $panels = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorID | ForEach-Object {
        [pscustomobject]@{
            active = $_.Active; instanceName = $_.InstanceName
            manufacturer = -join ($_.ManufacturerName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ })
            productCode = -join ($_.ProductCodeID | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ })
        }
    })
    $audit.brightness = [pscustomobject]@{
        instances = $brightnessInstances; methodInstances = $brightnessMethods; displays = $panels
        readSupported = @($brightnessInstances | Where-Object Active).Count -gt 0
        writeMethodExposed = @($brightnessMethods | Where-Object Active).Count -gt 0
        writeTested = $false
    }
} catch { Add-AuditError -Section 'brightness' -Failure $_ }

$audit.errors = @($auditErrors.ToArray())
$auditJson = $audit | ConvertTo-Json -Depth 12
if ($OutputPath) {
    $resolvedOutput = [IO.Path]::GetFullPath($OutputPath, (Get-Location).Path)
    $outputDirectory = Split-Path -Path $resolvedOutput -Parent
    if (-not (Test-Path -LiteralPath $outputDirectory)) { $null = New-Item -Path $outputDirectory -ItemType Directory }
    [IO.File]::WriteAllText($resolvedOutput, $auditJson + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
$auditJson
