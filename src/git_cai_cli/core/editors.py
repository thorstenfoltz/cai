# Editors that require an explicit blocking flag.
# Value is the flag that makes the editor block.

# Editors that are terminal-based and block by default
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
    "idea": "--wait",
    "idea64": "--wait",
    "pycharm": "--wait",
    "pycharm64": "--wait",
    "webstorm": "--wait",
    "goland": "--wait",
    "clion": "--wait",
    "kate": "--block",
}
