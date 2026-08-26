"""Economic index access (Section 8.3).

```
EconomicIndexProvider
|-- DemoIndexProvider          (default -- public app must run on this)
`-- ExternalLicensedProvider
```

`DemoIndexProvider` is the only provider the public app and the synthetic
generator ever depend on -- a deterministic, illustrative construction-cost
index, never a real published series (see `docs/DATA_PRIVACY.md` Section
6). `ExternalLicensedProvider` is an intentional architectural placeholder:
it documents where a real, license-verified index would plug in, without
implementing one, since no such license has been verified for this project.
"""

from __future__ import annotations

import datetime as dt
import math
from abc import ABC, abstractmethod

import pandas as pd

DEMO_INDEX_NAME = "INCC-DEMO"


class EconomicIndexProvider(ABC):
    """A monthly economic index, indexable by exact date."""

    @abstractmethod
    def get_series(self) -> pd.DataFrame:
        """Return the full index as columns ``reference_month, index_name, index_value``."""

    def value_at(self, date: dt.date | pd.Timestamp) -> float:
        """Index value for the month containing `date`.

        Falls back to the nearest available month for dates right at the
        edge of the generated window (inclusive rounding), rather than
        raising -- the provider owns its own date range, so this only
        triggers on boundary rounding, never on genuinely missing data.
        """
        series = self.get_series()
        month_end = pd.Timestamp(date) + pd.offsets.MonthEnd(0)
        exact = series.loc[series["reference_month"] == month_end, "index_value"]
        if len(exact) > 0:
            return float(exact.iloc[0])
        idx = (series["reference_month"] - month_end).abs().idxmin()
        return float(series.loc[idx, "index_value"])  # type: ignore[arg-type]


class DemoIndexProvider(EconomicIndexProvider):
    """Deterministic, illustrative demo construction-cost index.

    Not a real economic series. A smooth, seeded sine-modulated monthly
    ramp (~6%/year illustrative drift) -- fully determined by
    `reference_date` and `history_years`, with no per-call randomness, so
    it never needs to agree with any other RNG stream in the pipeline.
    """

    def __init__(
        self,
        reference_date: dt.date,
        history_years: int,
        index_name: str = DEMO_INDEX_NAME,
    ) -> None:
        self._reference_date = pd.Timestamp(reference_date)
        self._history_years = history_years
        self._index_name = index_name
        self._series: pd.DataFrame | None = None

    def get_series(self) -> pd.DataFrame:
        if self._series is None:
            self._series = self._generate()
        return self._series

    def _generate(self) -> pd.DataFrame:
        start = self._reference_date - pd.DateOffset(years=self._history_years, months=1)
        months = pd.date_range(start=start, end=self._reference_date, freq="ME")

        base_monthly_growth = 0.005
        seasonal_amplitude = 0.0015
        values = [100.0]
        for i in range(1, len(months)):
            growth = base_monthly_growth + seasonal_amplitude * math.sin(2 * math.pi * i / 12)
            values.append(values[-1] * (1.0 + max(growth, 0.0)))

        return pd.DataFrame(
            {
                "reference_month": months,
                "index_name": self._index_name,
                "index_value": values,
            }
        )


class ExternalLicensedProvider(EconomicIndexProvider):
    """Architectural placeholder for a real, license-verified index.

    Deliberately not implemented (Section 8.3): no external economic index
    has had its redistribution/usage license independently verified for
    this project. The public app and the synthetic generator must never
    depend on this class -- it exists only so the provider seam is visible
    in the codebase before such a license is ever verified. See
    `docs/DATA_PRIVACY.md` Section 6.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "ExternalLicensedProvider has no verified licensed data source. "
            "Use DemoIndexProvider. See docs/DATA_PRIVACY.md Section 6."
        )

    def get_series(self) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError
