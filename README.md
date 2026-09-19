# Ridge Runner

Godot 4.5.1 third-person 3D parkour. WASD moves, Space jumps, hold right mouse button to look, R restarts. Teal platforms are checkpoints. Twelve floating platforms, falling respawns you at your checkpoint.

This public repository contains only game source and GitHub-hosted playtest automation. No Studio/ClickUp secrets or personal infrastructure data are needed.

CI runs real Godot physics tests, exports Web and portable Windows candidates, then tests the Web build in Chromium. Successful runs publish downloadable prerelease candidates. These are prototypes, not signed/store-ready releases.

Reports are committed to the `build-results` branch under the source SHA. They distinguish build, browser smoke and native device acceptance. Windows native execution and mobile real-device testing are not claimed by Linux CI.

For a Web ZIP: extract it, run `python3 -m http.server 8060` in that folder, then open `http://localhost:8060`. Do not double-click index.html. The Windows ZIP contains a portable executable; unsigned prototypes may trigger platform warnings.

Engine licensing: https://godotengine.org/license/ . Original game source is MIT licensed.
