"""
Editors that require an explicit blocking flag.
Value is the flag that makes the editor block.
Editors that are terminal-based and block by default
"""

TERMINAL_EDITORS = {
    "vi",
    "vim",
    "nano",
    "nvim",
}

EDITOR_BLOCK_FLAGS = {
    "code": "--wait",
    "code-insiders": "--wait",
    "subl": "--wait",
    "sublime_text": "--wait",
    "atom": "--wait",
    "pycharm": "--wait",
    "pycharm64": "--wait",
    "kate": "--block",
}
