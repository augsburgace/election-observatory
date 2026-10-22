"""Shared election-environment labels; these do not encode party behavior."""
from __future__ import annotations


def election_type(year: int) -> str:
    return 'presidential' if year % 4 == 0 else 'midterm' if year % 2 == 0 else 'off_year'
