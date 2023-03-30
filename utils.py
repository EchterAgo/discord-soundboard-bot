import os
import typing

def find_files(path: str) -> typing.Iterator[str]:
    for root, _, files in os.walk(path, topdown=True):
        for file in files:
            yield os.path.relpath(os.path.join(root, file), path)
