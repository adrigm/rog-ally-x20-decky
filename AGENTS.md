# Project instructions

- Do not add, enable, or run GitHub Actions. Build, tests, packaging and release validation run locally.
- Use focused feature branches and descriptive commits. Keep `main` usable.
- Never commit local diagnostics, credentials, Steam/Decky settings, logs, virtual environments or installed dependencies.
- The target is Windows x64 and Decky Loader. Validate the distributed package inside Decky, not only from the repository working directory.
- Keep Python imports under `py_modules/ally_system_control`; `main.py` is the Decky entry point.
- Do not apply saved volume or brightness on startup, reload or unload. Read current Windows state first.
- Keep deployment limited to this plugin's directory, back up existing copies, and do not restart Steam or other plugins unnecessarily.
- Run appropriate local checks for each change and record the actual validation and remaining hardware checks.
