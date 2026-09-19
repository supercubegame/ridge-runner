# Ridge Runner
Godot 4.5.1 + GDScript + Compatibility. No native plugins.
Gate: python3 tools/engine_gate.py, with GODOT pointing at the real editor.
Web build: python3 tools/ci_build.py. Browser smoke: node tools/browser_smoke.cjs.
CI reports must include SHA, run ID, logs and explicit failures. No fabricated pass.
Pure gameplay formulas live in rules.gd. Speed, jump, gravity, height and gaps are coupled.
Only public game source belongs here. No SSH addresses, workspace data or credentials.
One writer per branch. Do not merge without approval.
Public release candidates are not store-signed or device-certified builds.
