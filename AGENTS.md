## General

Always use this Python on Mac:
/Users/jamesb/.pyenv/versions/3.13.0/envs/py13/bin/python
and this Python on Linux:
/home/jamesb/py313/bin/python

## Gerber viewer reload

Run `./gerbv-reload` at the end of every board-changing operation so the
user's Gerber view updates. On macOS it must be run with elevated execution
outside the workspace sandbox: sandboxed `osascript` cannot access System
Events and fails with error `-10827`, even while Gerbv is running.

## PCB manufacturing preflight

When the user asks to preflight a PCB, check it before manufacture, or decide
whether manufacturing outputs are ready to submit, use the repo-local
`pcb-manufacturing-preflight` skill.

Do not describe a board as ready for manufacture unless its automated preflight
passes and the skill's manual CAM/visual checks have been completed. Treat
numeric construction requirements, such as a particular GML contour count, as
board-profile settings rather than universal CuFlow rules.
