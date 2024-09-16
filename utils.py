import os
import typing
import unicodedata


def find_files(path: str) -> typing.Iterator[str]:
    for root, _, files in os.walk(path, topdown=True):
        for file in files:
            yield os.path.relpath(os.path.join(root, file), path)


# From https://stackoverflow.com/a/29247821
def normalize_caseless(text):
    return unicodedata.normalize("NFKD", text.casefold())


def caseless_equal(left, right):
    return normalize_caseless(left) == normalize_caseless(right)


def caseless_in(left, right):
    return normalize_caseless(left) in normalize_caseless(right)
