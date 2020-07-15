
from typing import Iterable, Optional

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from ..ipod.path import iPath


class FileCompleter(Completer):
    _complete_with_dirs = {'cd'}
    _complete_with_files = {'cat', 'rm', 'head', 'touch', 'cp'}
    _complete_with_any = {'stat', 'ls', 'lst', 'mkdir'}
    _complete_cmds = _complete_with_dirs.union(_complete_with_files).union(_complete_with_any)

    def __init__(self):
        self.cwd = None  # type: Optional[iPath]
        self._path_cache = {}

    def __call__(self, cwd: iPath):
        self.cwd = cwd
        self._path_cache = {self.cwd: [p.name for p in self.cwd.iterdir()]}
        return self

    def _get_paths(self, cmd: str, path: str):
        if cmd in self._complete_cmds:
            if '/' in path:
                if not path.endswith('/'):
                    path = path.rsplit('/', 1)[0] or '/'
                cwd = self.cwd.joinpath(path).resolve()
            else:
                cwd = self.cwd

            if cwd not in self._path_cache:
                prefix = cwd.as_posix() if path.startswith('/') and path != '/' else cwd.as_posix()[1:]
                self._path_cache[cwd] = [f'{prefix}/{p.name}' for p in cwd.iterdir()]

            return self._path_cache[cwd]
        return None

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        cmd, mid, last = '', '', ''
        text_before_cursor = document.text_before_cursor
        try:
            cmd, remainder = text_before_cursor.split(maxsplit=1)
        except ValueError:
            cmd = text_before_cursor
            if not text_before_cursor.endswith(' '):
                return
        else:
            try:
                mid, last = remainder.rsplit(maxsplit=1)
            except ValueError:
                last = remainder

        lower_last = last.lower()
        if file_names := self._get_paths(cmd, last):
            for file_name in file_names:
                if file_name.lower().startswith(lower_last):
                    yield Completion(file_name, -len(last))
