# Components

The installer bundles CLIProxyAPI 8.0.16 from https://github.com/router-for-me/CLIProxyAPI under MIT. Its full license is installed as ClaudeGemini/CLIProxyAPI-LICENSE.txt.

The executables also use Python (PSF license), PySide6 / Qt 6 (LGPL-3.0; PySide6 also offers GPL licensing), PyYAML (MIT), bcrypt (Apache-2.0), cryptography (Apache-2.0 / BSD), and tzdata (Apache-2.0 / public-domain IANA data). PyInstaller uses GPL with its bootloader distribution exception. See the respective projects and dependency lists in requirements.txt and requirements-cli.txt. The account manager uses Qt; the installer uses Python's standard-library Tkinter.

Google, Gemini, Antigravity, Claude and Codex are names of third-party products. This project is independent of their vendors.

# Additional upstream improvements

Quota availability, model catalog and client-routing improvements were adapted from
[nikitaeight24family/GeminiAccounts](https://github.com/nikitaeight24family/GeminiAccounts),
reviewed at commit `24877921bc30642c5bfc86ff03bc640212507fef` (MIT).
The PySide6 interface, translations and independent encrypted API profiles are retained.

ChatGPT OAuth account controls, quota reset handling and account-state classification
were adapted from the same MIT-licensed upstream at commit `cfec649`.
The Qt interface, opaque client routes and independent API-key fallback are local adaptations.

Manual account priorities, quota reserves and compact quota summaries were adapted
from [nikitaeight24family/Omni](https://github.com/nikitaeight24family/Omni)
at commit `1b7c6ac8e222435fe8e7b0aaeb79536ae01f62d3` (MIT).
The Qt controls, retained subscription cards and native Claude pool support are local adaptations.
