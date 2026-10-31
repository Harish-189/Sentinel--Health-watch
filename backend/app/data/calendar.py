"""Public holiday calendar (fictional holidays). This is system knowledge, not health data."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# (month, day, name); recurring every year
RECURRING: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Founders Day"),
    (3, 21, "Spring Lantern"),
    (7, 1, "Midyear Rest"),
    (9, 10, "Harvest Festival"),
    (12, 25, "Winterfest"),
)


@dataclass
class Calendar:
    dates: pd.DatetimeIndex
    holidays: dict[int, str] = field(default_factory=dict)  # day index -> name

    def add(self, day: int, name: str) -> None:
        if 0 <= day < len(self.dates):
            self.holidays[day] = name

    def flags(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(is_holiday, pre_holiday, post_holiday) as float arrays over all days."""
        n = len(self.dates)
        hol = np.zeros(n)
        for d in self.holidays:
            hol[d] = 1.0
        pre = np.zeros(n)
        post = np.zeros(n)
        pre[:-1] = hol[1:]
        post[1:] = hol[:-1]
        return hol, np.clip(pre - hol, 0, 1), np.clip(post - hol, 0, 1)


def build_calendar(dates: pd.DatetimeIndex) -> Calendar:
    cal = Calendar(dates)
    for i, ts in enumerate(dates):
        for month, day, name in RECURRING:
            if ts.month == month and ts.day == day:
                cal.add(i, name)
    return cal
