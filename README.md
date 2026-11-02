# Ally System Control para Decky en Windows

Plan de un plugin para controlar Windows desde Steam Big Picture en la ROG Xbox Ally X. La primera versión incluirá volumen maestro, silencio y brillo de la pantalla integrada.

Estado a 2 de noviembre de 2026: planificación y auditoría terminadas; todavía no hay un plugin implementado ni se han instalado dependencias.

- [Plan técnico y fases](docs/PLAN.md).
- [Herramientas e instrucciones de instalación](docs/SETUP.md).
- [Informe del equipo comprobado](docs/environment-audit.json).
- [Diagnóstico reproducible de solo lectura](scripts/diagnose-environment.ps1).

La auditoría detectó Python 3.15.2, Git instalado fuera del PATH, Steam y procesos de Decky activos. Faltan Node.js/npm y pnpm. La pantalla integrada expone lectura y método de escritura de brillo por WMI; no se ha probado ninguna escritura.

Para repetir el diagnóstico desde PowerShell 7:

```powershell
.\scripts\diagnose-environment.ps1
```

Para guardar el informe local:

```powershell
.\scripts\diagnose-environment.ps1 -OutputPath .\docs\environment-audit.json
```

El informe contiene rutas del usuario y detalles del equipo. Está excluido de Git por defecto.
