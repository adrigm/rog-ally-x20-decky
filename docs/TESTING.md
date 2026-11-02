# Validación de 0.1.0-alpha.1

Fecha: 2 de noviembre de 2026. Las pruebas se ejecutan localmente; no se utiliza GitHub Actions.

## Entorno comprobado

Windows 11 x64, ROG Xbox Ally X comunicada como RC74XA, Ryzen AI Z2 Extreme y Radeon 890M. Entorno de desarrollo: Node 26.13.0, pnpm 9.15.9, Python 3.14.10 y comtypes 1.4.17.

El runtime y la versión de la instalación de Decky siguen pendientes de medir desde el plugin cargado. Python 3.14.10 en una terminal no demuestra por sí solo que el runtime incorporado en Decky sea compatible.

## Comprobaciones automatizadas

`scripts/build.ps1` ejecuta:

1. TypeScript sin emisión y compilación Rollup para Decky.
2. Pruebas del frontend: agrupación de escrituras, orden de respuestas, cambio de dispositivo, sondeo sin solapamiento y limpieza.
3. Pruebas Python del contrato, identidad de dispositivo, separación de trabajadores, cancelación, errores y cierre.
4. Pruebas del verificador de paquetes y del wrapper de diagnóstico.

`scripts/package.ps1` incluye dependencias y licencias, verifica la estructura del ZIP y comprueba imports en un proceso aislado desde una extracción temporal. Esa verificación no ejecuta setters ni carga el plugin en Steam.

Resultado actual: **44 pruebas correctas** (26 del backend, 11 del frontend y 7 de herramientas), typecheck y build sin advertencias. También pasan la verificación de importaciones aisladas del ZIP y `git diff --check`.

## Hardware

`scripts/smoke-backend.ps1` ha confirmado lectura real desde el paquete distribuible: altavoces predeterminados, volumen 55 %, mute desactivado y brillo 100 % con 101 niveles disponibles. Ambos trabajadores terminaron correctamente. Estos porcentajes son una observación puntual, no ajustes que el plugin imponga.

Prueba de escritura real desde el paquete reconstruido:

| Control | Ensayo | Resultado final |
| --- | --- | --- |
| Volumen | 55 → 54 → 55 % | Confirmado; restaurado a 55 %. |
| Brillo integrado | 100 → 99 → 100 % | Confirmado tras esperar el valor efectivo; restaurado a 100 %. |
| Silencio | Escritura del mismo estado desactivado | Confirmado sin interrumpir reproducción; alternancia audible pendiente. |
| Recursos | Cierre tras el ensayo | Ambos trabajadores terminados, colas vacías y sin errores. |

La primera prueba de brillo reveló que el proveedor aplicaba el cambio pero devolvía una salida vacía. El código se corrigió para validar `ReturnValue` cuando existe y exigir confirmación mediante lectura posterior; una respuesta vacía por sí sola no se considera éxito. El ensayo completo se repitió con éxito después de la corrección.

Los cambios se hicieron con identificación del dispositivo y restauración condicionada a que no aparecieran cambios concurrentes. El estado final confirmado fue volumen 55 %, mute desactivado y brillo 100 %.

## Despliegue de desarrollo

El paquete completo se ha copiado a `%USERPROFILE%\homebrew\plugins\ally-system-control` mediante `deploy-dev.ps1`. Era la primera instalación de este plugin; no fue necesario reemplazar una copia anterior. No se reiniciaron Steam, Decky ni los otros plugins.

La copia en disco está comprobada. El usuario ha confirmado que «Ally System Control» aparece en Decky y muestra los valores de volumen y brillo. Esta comprobación confirma la carga del panel y la comunicación con el backend en su instalación real; la revisión visual completa y el manejo con mando siguen pendientes.

## Validación manual pendiente

- Registrar las versiones de loader y Python que devuelve «Mostrar diagnóstico»; la carga y las lecturas del panel ya están confirmadas por el usuario.
- Comprobar presentación, foco y navegación completa con mando y pantalla táctil.
- Alternar silencio desde el panel y confirmar el efecto audible y la conservación del nivel.
- Comprobar cambios externos desde botones físicos, Windows y Armoury Crate.
- Cambiar la salida a auriculares, USB o Bluetooth y verificar que no se aplican peticiones antiguas al nuevo dispositivo.
- Suspender/reanudar y volver a abrir el panel.
- Confirmar que el brillo del monitor externo no cambia.
- Cargar, recargar y descargar dentro de Decky sin duplicar tareas o aplicar valores guardados.
- Comprobar disponibilidad del menú durante un juego de Steam y las limitaciones de audio exclusivo.

La sesión de Computer Use se interrumpió al detectar Escape físico. No se continuó automatizando la interfaz ni se reinició Steam para completar estas pruebas.
