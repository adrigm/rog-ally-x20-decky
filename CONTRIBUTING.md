# Desarrollo y gestión del repositorio

Las comprobaciones se ejecutan localmente. No añadir workflows de GitHub Actions ni habilitar Actions en este repositorio.

## Ramas y commits

- `main` contiene el estado integrado del proyecto.
- Usar ramas con un objetivo concreto: `feat/...`, `fix/...` o `docs/...`.
- Separar cambios de backend, interfaz, herramientas y documentación en commits revisables.
- Describir el resultado con prefijos `feat:`, `fix:`, `build:` o `docs:`.
- Abrir una pull request con los cambios, validación realizada y comprobaciones manuales pendientes.
- Integrar después de revisión y validación local; conservar los commits relevantes y retirar la rama cuando deje de ser necesaria.

## Comprobaciones antes de integrar

```powershell
.\scripts\build.ps1
.\scripts\package.ps1 -SkipBuild
git diff --check
```

Si el cambio afecta a Windows, realizar también `smoke-backend.ps1` y las pruebas de hardware pertinentes de [TESTING.md](docs/TESTING.md). No confundir pruebas con adaptadores simulados con comprobación real del dispositivo.

Las pruebas automatizadas normales no escriben volumen, mute o brillo. Cualquier ensayo manual de escritura debe conservar el estado previo y restaurarlo solo si el usuario o Windows no lo han sustituido entretanto.

No versionar informes de diagnóstico, rutas privadas, credenciales, configuraciones de Steam/Decky, `.venv`, `node_modules` ni ZIP generados. Mantener las dependencias fijadas y sus licencias en la distribución.
