import typing
import unicodedata
from pathlib import Path


def find_files(path: Path) -> typing.Iterator[str]:
    path = Path(path)
    for file_path in path.rglob('*'):
        if file_path.is_file():
            yield str(file_path.relative_to(path))


# From https://stackoverflow.com/a/29247821
def normalize_caseless(text):
    return unicodedata.normalize("NFKD", text.casefold())


def caseless_equal(left, right):
    return normalize_caseless(left) == normalize_caseless(right)


def caseless_in(left, right):
    return normalize_caseless(left) in normalize_caseless(right)
