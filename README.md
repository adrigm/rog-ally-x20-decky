# Ally System Control

Plugin de Decky Loader para controlar **volumen maestro, silencio y brillo de la pantalla integrada** en Windows 11, pensado para la ROG Xbox Ally X. [Repositorio público](https://github.com/adrigm/rog-ally-x20-decky).

Versión inicial: `0.1.0-alpha.1`. Incluye controles nativos de Decky, sincronización con Windows mientras el panel está abierto y detección de cambios de dispositivo. No modifica valores al cargar, recargar o cerrar el plugin.

## Estado

El código compila y pasa 44 pruebas locales del backend, de las colas de la interfaz y del empaquetado. Se han comprobado lecturas y cambios reales de volumen y brillo, con restauración del estado previo, en una ROG Xbox Ally X con Ryzen AI Z2 Extreme. La validación visual y de mando dentro de Decky sigue pendiente; consulta [las comprobaciones realizadas y pendientes](docs/TESTING.md).

Decky para Windows es experimental. Este plugin se integra en Steam Big Picture: la primera versión controla la salida de audio predeterminada y el panel integrado, sin mezclador por juego ni brillo de monitores externos.

## Desarrollo local

Requisitos: Windows x64, PowerShell 7, Node.js 26 LTS, pnpm 9.15.9 y Python 3.14 x64. Git y GitHub CLI permiten gestionar el repositorio. [Preparación del entorno](docs/SETUP.md).

```powershell
.\scripts\build.ps1
.\scripts\package.ps1 -SkipBuild
.\scripts\smoke-backend.ps1
```

`build.ps1` instala dependencias del proyecto y ejecuta typecheck, pruebas y compilación. `package.ps1` crea el ZIP y su SHA256 en `artifacts`, y verifica las importaciones desde una extracción limpia. `smoke-backend.ps1` consulta el hardware sin cambiar valores.

Si Python no se localiza automáticamente, los scripts admiten `-PythonPath C:\ruta\python.exe`. Las dependencias Python se aíslan en `.venv` y se incluyen en el ZIP; el usuario final no necesita Python global para ejecutar el plugin con el loader empaquetado.

## Instalación de desarrollo

Con Decky para Windows ya instalado y el paquete generado:

```powershell
.\scripts\deploy-dev.ps1
```

Se copia únicamente `ally-system-control` a `%USERPROFILE%\homebrew\plugins`, con copia de seguridad si ya existe. El script no reinicia Steam ni Decky. La carga/recarga se debe comprobar desde la instalación de Decky existente; copiar archivos no demuestra que el panel esté cargado.

Para otra ubicación, usa `-HomebrewPath C:\ruta\homebrew`. Para restaurar una copia, usa `-RestoreBackupPath` con la ruta que imprimió el despliegue.

## Documentación

- [Plan técnico y ampliaciones](docs/PLAN.md).
- [Herramientas y preparación](docs/SETUP.md).
- [Validación local y pruebas manuales](docs/TESTING.md).
- [Flujo de ramas y commits](CONTRIBUTING.md).
- [Diagnóstico reproducible de solo lectura](scripts/diagnose-environment.ps1).

Los informes del equipo, credenciales, dependencias instaladas y artefactos generados quedan fuera de Git. **GitHub Actions está deshabilitado**: compilación, pruebas y empaquetado se ejecutan localmente.

Licencia [BSD-3-Clause](LICENSE). `comtypes` se distribuye con su propia licencia dentro del paquete.
