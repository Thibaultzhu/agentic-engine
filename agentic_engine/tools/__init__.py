"""Built-in tools. All implementations are minimal and original."""
from .bash import bash_run
from .diff import git_diff, git_log, git_status
from .files import grep_text, list_dir, read_file, write_file
from .screen import (
    keyboard_hotkey,
    keyboard_type,
    mouse_click,
    mouse_move,
    screen_grab,
    screen_grab_b64,
    screen_size,
)
from .web import web_fetch

__all__ = [
    "bash_run",
    "read_file",
    "write_file",
    "list_dir",
    "grep_text",
    "web_fetch",
    "git_status",
    "git_diff",
    "git_log",
    "screen_grab",
    "screen_grab_b64",
    "screen_size",
    "mouse_click",
    "mouse_move",
    "keyboard_type",
    "keyboard_hotkey",
]
