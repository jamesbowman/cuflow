## General

Always use this Python on Mac:
/Users/jamesb/.pyenv/versions/3.13.0/envs/py13/bin/python
and this Python on Linux:
/home/jamesb/py313/bin/python

## PCB manufacturing preflight

When the user asks to preflight a PCB, check it before manufacture, or decide
whether manufacturing outputs are ready to submit, use the repo-local
`pcb-manufacturing-preflight` skill.

Do not describe a board as ready for manufacture unless its automated preflight
passes and the skill's manual CAM/visual checks have been completed. Treat
numeric construction requirements, such as a particular GML contour count, as
board-profile settings rather than universal CuFlow rules.
