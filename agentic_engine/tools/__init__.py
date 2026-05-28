"""Built-in tools. All implementations are minimal and original."""
from .bash import bash_run
from .files import read_file, write_file, list_dir, grep_text
from .web import web_fetch
from .diff import git_status, git_diff, git_log
from .screen import (
    screen_grab,
    screen_grab_b64,
    screen_size,
    mouse_click,
    mouse_move,
    keyboard_type,
    keyboard_hotkey,
)

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
