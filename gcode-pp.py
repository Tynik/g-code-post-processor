import os
import time
import argparse
import typing as t
from threading import Thread
from yaml import load
from datetime import datetime

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


class SourceCode:
    def __init__(self, stream: t.TextIO):
        self._count_layers = None
        self._stream = stream

        for code_line in stream:
            try:
                code_line.index(';LAYER_COUNT:')
                self._count_layers = int(code_line.split(':')[1])
            except:
                pass

        stream.seek(0)

    def __iter__(self):
        for code_line in self._stream:
            yield code_line

    def get_count_layers(self):
        return self._count_layers

    count_layers = property(get_count_layers)

    def close(self):
        self._stream.close()


class Watcher(Thread):
    _stopped = False

    def __init__(self, code_filename, rule_ids, target: t.Callable):
        super(Watcher, self).__init__(kwargs={'code_filename': code_filename})

        self._rule_ids = rule_ids
        self._target = target

    def run(self) -> None:
        started_time = None

        while 1:
            if self._stopped:
                break

            modified_time = os.stat(self._kwargs['code_filename']).st_mtime
            if started_time is None or started_time < modified_time:
                if started_time is not None and started_time < modified_time:
                    for rule_id in self._rule_ids:
                        self._target(rule_id)

                started_time = modified_time

            time.sleep(1)

    def stop(self):
        self._stopped = True


class GCodePP:
    def __init__(self, code_filename, output_filename=None, watch=False):
        self._code_filename = code_filename
        self._output_filename = output_filename
        self._watch = watch
        self._count_layers = None
        self._rule_ids = []

        self._watcher = None
        if watch:
            self._watcher = Watcher(code_filename, self._rule_ids, self.compile)
            self._watcher.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._watcher:
            self._watcher.stop()

    def compile(self, rule_id: str):
        print('[' + datetime.now().strftime("%H:%M:%S") + '] Postprocess "' + self._code_filename + '" with a rule "' + rule_id + '"')

        if self._watcher:
            try:
                self._rule_ids.index(rule_id)
            except ValueError:
                self._rule_ids.append(rule_id)

        source_code = None
        try:
            source_code = SourceCode(open(self._code_filename))

            try:
                fn = 'rules[' + rule_id + '].yml'
                rules = load(open(fn), Loader)
                for rule in rules:
                    if rule['layer'] >= source_code.count_layers:
                        raise ValueError('The layer number [' + str(rule['layer']) + '] cannot be more than count layers')
            except FileNotFoundError:
                raise NameError('Rules with a filename "' + fn + '" cannot be find')

            if self._output_filename is None:
                filename, _ = os.path.splitext(self._code_filename)
                self._output_filename = filename

            with open(self._output_filename + '[' + rule_id + ']' + '.gcode', 'w+') as out:
                for code_line in source_code:
                    for rule in rules:
                        layer_comment = ';LAYER:' + str(rule['layer']) + '\n'

                        code_line = code_line.replace(
                            layer_comment,
                            layer_comment + rule['code'] + '\n', 1)

                    out.write(code_line)

        finally:
            if source_code is not None:
                source_code.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('gcode_source_filename', help='Source filename with GCode to process it')
    parser.add_argument('rules', nargs='+', help='The rules applied for the GCode source file')
    parser.add_argument('--watch', action='store_true', help='Reapply rules when GCode source file changed')
    args = parser.parse_args()

    g = GCodePP(args.gcode_source_filename, watch=args.watch)
    for rule in args.rules:
        g.compile(rule)


if __name__ == '__main__':
    main()

