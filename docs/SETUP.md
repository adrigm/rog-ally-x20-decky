# Herramientas para desarrollar el plugin en Windows

Estado actualizado durante la implementación del 2 de noviembre de 2026. Node.js, pnpm, GitHub CLI y Python 3.14 ya están instalados en el equipo de desarrollo. Los pasos de instalación se conservan para preparar otro entorno.

## 1. Qué hay y qué falta

| Herramienta | Estado comprobado | Acción |
| --- | --- | --- |
| Python | CPython 3.15.2 y 3.14.10 x64 en paralelo. | Usar 3.14 para `.venv`; conservar 3.15. |
| pip / venv / ctypes | Presentes; pip 26.2.2. | Reutilizar para tareas generales; aislar las dependencias del proyecto. |
| Git | 2.56.0.windows.4 en `C:\Program Files\Git\cmd\git.exe`. | No reinstalar. Resolver PATH de la nueva sesión o usar la ruta absoluta. |
| Node.js / npm | Node 26.13.0 y npm 11.20.0. | Disponibles; los scripts tienen fallback si la terminal conserva un PATH antiguo. |
| pnpm | 9.15.9. | Disponible. |
| GitHub CLI | 2.103.3, autenticado. | Gestión del repositorio público; Actions deshabilitado. |
| Steam | Instalado y CEF activo en loopback. | Aprovechar la configuración existente; comprobar Big Picture. |
| Decky | Procesos, carpeta de plugins y listener activos. | Identificar versión y runtime; no reinstalar de entrada. |
| VS Code | Instalado. | Editor opcional ya disponible. |
| winget | v1.29.380 operativo. | Puede instalar las herramientas que faltan. |
| PowerShell | 7.6.5 en la auditoría. | Usar PowerShell 7 para el diagnóstico y los futuros scripts. |
| .NET | Runtimes 8.0.21/8.0.33; `--list-sdks` vacío. | No hace falta SDK para el diseño elegido. |
| comtypes / pruebas | comtypes 1.4.17 en `.venv` y en staging; unittest estándar. | No se necesitan pycaw ni pytest. |
| Rust / Cargo / CMake | No encontrados. | No necesarios para el MVP. |
| WSL | `wsl.exe` presente; no se han inspeccionado distribuciones. | No es requisito. Docker tampoco es requisito para este MVP. |

## 2. Instalación que sí hace falta para empezar

Instala **Node.js 26 LTS x64**. Tanto la web oficial como `winget show` ofrecían 26.13.0 en la comprobación. Node LTS puede cambiar de versión; el comando siguiente fija la versión verificada hoy. [Descargas oficiales](https://nodejs.org/en/download), [estado de las ramas](https://nodejs.org/en/about/previous-releases).

```powershell
winget install --id OpenJS.NodeJS.LTS --exact --version 26.13.0 --source winget
```

También se puede usar el instalador x64 desde la web oficial. El instalador puede mostrar UAC. No selecciones herramientas de compilación adicionales: el MVP no las necesita.

Cierra y vuelve a abrir la terminal; si Codex no recibe el PATH actualizado, vuelve a abrir la aplicación. Comprueba:

```powershell
node --version
npm.cmd --version
```

Después instala **pnpm 9.15.9**:

```powershell
npm.cmd install --global pnpm@9.15.9
pnpm.cmd --version
```

Se usa `.cmd` para que PowerShell no dependa de la política de ejecución de los wrappers `.ps1`. No hace falta cambiar esa política para ejecutar npm o pnpm. La versión 9 es la que solicita la plantilla de plugins; no se sustituirá automáticamente por el pnpm más reciente. [Requisito de la plantilla](https://github.com/SteamDeckHomebrew/decky-plugin-template#dependencies), [release pnpm 9.15.9](https://github.com/pnpm/pnpm/releases/tag/v9.15.9).

Al crear el plugin se fijará `packageManager` a `pnpm@9.15.9`, se conservará un único lockfile y se verificará la combinación Node 26/pnpm 9 con el build adaptado a Windows. La CI del loader usa Node 26, pero la prueba del plugin sigue siendo necesaria. [CI de Decky](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.3.1/.github/workflows/build.yml).

## 3. Git ya está instalado

Esta llamada funciona en el equipo actual:

```powershell
& 'C:\Program Files\Git\cmd\git.exe' --version
```

Para utilizar `git` por nombre sin modificar ajustes permanentes se puede añadirlo solo a la terminal actual:

```powershell
$env:Path = 'C:\Program Files\Git\cmd;' + $env:Path
git --version
```

Si una terminal nueva ya encuentra Git, ese cambio no hace falta. No hay motivo para descargar otra copia.

## 4. Python para la fase de backend

Tu **Python 3.15.2 funciona** y se mantendrá. El ejecutable oficial de Decky v3.3.1 lleva Python 3.14.8 incorporado y el loader declara un rango de desarrollo inferior a 3.15. Antes de fijar el entorno se obtendrá el runtime de tu instalación real mediante un plugin mínimo. [Rango soportado](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.3.1/backend/pyproject.toml), [runtime de la compilación oficial](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.3.1/.github/workflows/build.yml).

Para desarrollar y probar el backend en la línea 3.14, se recomienda **Python 3.14 x64 en paralelo**, sin sustituir la versión actual. `winget show` ofrecía 3.14.10; no ofrecía 3.14.8. El patch 3.14.10 permite preparar un entorno de la misma línea; el test decisivo seguirá siendo dentro del loader.

Este paso corresponde a la preparación del backend, después de identificar el runtime instalado:

```powershell
winget install --id Python.Python.3.14 --exact --version 3.14.10 --architecture x64 --source winget
py -3.14 --version
```

No se necesita Python global para ejecutar el binario empaquetado de Decky. Esta instalación adicional sirve para pruebas, empaquetado de dependencias y herramientas de desarrollo.

Cuando se implemente el backend, desde la raíz del proyecto:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe --version
```

Se usan llamadas explícitas a `.venv\Scripts\python.exe`, sin necesidad de activar el entorno ni de alterar políticas de PowerShell. `requirements.txt` fija comtypes 1.4.17; `build.ps1` crea el entorno, instala esta dependencia y ejecuta las pruebas locales.

`comtypes` será la dependencia propuesta para COM/WMI y se probará también dentro de Decky. `pycaw`, `pywin32`, Poetry y PyInstaller no son requisitos iniciales del plugin; no se va a recompilar el loader para añadir estos controles. [comtypes](https://github.com/enthought/comtypes).

## 5. Steam y Decky existentes

Se ha encontrado `%USERPROFILE%\homebrew\plugins` con cinco plugins y procesos de Decky que escuchan en loopback. La versión instalada no pudo leerse de las rutas/procesos disponibles. El puerto CEF de Steam está activo y existe su marcador `.cef-enable-remote-debugging`. No hace falta crear otra instalación antes de comprobar esta.

La siguiente fase identificará la versión en la interfaz de Decky y registrará Python, arquitectura y ruta de datos desde un plugin mínimo. Se verificará carga/descarga y una llamada al backend.

Solo si hace falta reparar o migrar se utilizará el upstream oficial x64, cuya release de referencia es [Decky v3.3.1](https://github.com/SteamDeckHomebrew/decky-loader/releases/tag/v3.3.1). Los artefactos oficiales tienen estos hashes publicados:

| Archivo | SHA256 |
| --- | --- |
| `PluginLoader-win.exe` | `68ca1ebf3711c23057bd6734a8055399119b31d8812b254f8918f1f69af4d142` |
| `PluginLoader-win-noconsole.exe` | `8b7a36146591a3d3b54ba69c986dc508e2aea21f56652520b21e1126deebe65b` |

La migración requeriría respaldar la instalación actual y comprobar su modo de arranque. Estos datos no son una instrucción para ejecutar un segundo loader junto al que ya funciona.

## 6. Comprobación después de instalar

Desde una nueva terminal PowerShell 7, en la raíz del proyecto:

```powershell
node --version
npm.cmd --version
pnpm.cmd --version
& 'C:\Program Files\Git\cmd\git.exe' --version
.\scripts\diagnose-environment.ps1 -OutputPath .\docs\environment-audit.json
```

Resultado esperado: Node 26.13.0, npm operativo, pnpm 9.15.9, Git operativo y el informe actualizado sin errores de inventario. El Python 3.14 se comprobará expresamente con `py -3.14` cuando se instale; el diagnóstico principal puede seguir resolviendo 3.15 como intérprete predeterminado.

El script recoge herramientas, hardware, brillo WMI, presencia de Steam/Decky y listeners locales. No establece volumen o brillo, no reinicia aplicaciones y no comprueba la interfaz de Decky. Solo guarda un archivo cuando se indica `-OutputPath`; el informe local está ignorado por Git.

## 7. Herramientas que quedan fuera de esta primera instalación

No se necesitan Docker Desktop, WSL/Linux, Rust, CMake, Visual Studio Build Tools, un SDK .NET ni un controlador ASUS propio para el plugin Python/TypeScript propuesto. React, TypeScript y Rollup se instalarán como dependencias del proyecto, no como herramientas globales.

Si una comprobación real obliga a cambiar esa elección, primero se documentará el fallo y la dependencia concreta que lo resuelve. La implementación y sus scripts ya están disponibles; [TESTING.md](TESTING.md) distingue lo comprobado de la validación pendiente dentro de Decky.
