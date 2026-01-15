"""Biologic price loader / resolver (Step 2-1)

使い方:
  - 起動時に一度読み込む:
      from src.biologic_price import init_biologic_prices
      init_biologic_prices('reports/biologic_drug_price_2025-04.csv')

  - 実行時に価格を参照:
      from src.biologic_price import get_biologic_price, BiologicPriceNotFoundError
      try:
          price = get_biologic_price('ヌーカラ皮下注１００ｍｇペン')
      except BiologicPriceNotFoundError:
          raise
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict

class BiologicPriceError(Exception):
    """基底例外"""

class BiologicPriceNotLoadedError(BiologicPriceError):
    """価格テーブルがまだロードされていない"""

class BiologicPriceNotFoundError(BiologicPriceError):
    """要求された exact_item_name が見つからない"""

class BiologicPriceDataError(BiologicPriceError):
    """CSV の形式や値に問題がある"""

class BiologicPriceDuplicateError(BiologicPriceError):
    """exact_item_name の重複"""

_PRICES: Dict[str, int] | None = None

def _parse_price_to_int(raw: str) -> int:
    if raw is None:
        raise BiologicPriceDataError("price_yen is missing")
    s = str(raw).strip()
    if s == "":
        raise BiologicPriceDataError("price_yen is empty")
    s2 = s.replace(",", "")
    if not re.fullmatch(r"\d+", s2):
        raise BiologicPriceDataError(f"price_yen is not integer: {raw!r}")
    return int(s2)

def load_biologic_prices(csv_path: str | Path) -> Dict[str, int]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Biologic price CSV not found: {path}")

    required = {"exact_item_name", "price_yen"}
    prices: Dict[str, int] = {}

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = set(reader.fieldnames or [])
        if not required.issubset(header):
            missing = required - header
            raise BiologicPriceDataError(
                f"Missing required columns: {', '.join(missing)}"
            )

        for i, row in enumerate(reader, start=2):
            name = (row.get("exact_item_name") or "").strip()
            if name == "":
                raise BiologicPriceDataError(
                    f"Row {i}: exact_item_name is empty"
                )
            if name in prices:
                raise BiologicPriceDuplicateError(
                    f"Duplicate exact_item_name at row {i}: {name!r}"
                )
            price = _parse_price_to_int(row.get("price_yen"))
            prices[name] = price

    if not prices:
        raise BiologicPriceDataError("No price rows found in CSV")

    return prices

def init_biologic_prices(csv_path: str | Path) -> None:
    global _PRICES
    _PRICES = load_biologic_prices(csv_path)

def get_biologic_price(exact_item_name: str) -> int:
    if _PRICES is None:
        raise BiologicPriceNotLoadedError(
            "Biologic prices not initialized. "
            "Call init_biologic_prices() at startup."
        )
    key = (exact_item_name or "").strip()
    if key == "":
        raise BiologicPriceNotFoundError(
            "Requested exact_item_name is empty"
        )
    try:
        return _PRICES[key]
    except KeyError:
        raise BiologicPriceNotFoundError(
            f"Biologic price not found for: {exact_item_name!r}"
        )

def is_loaded() -> bool:
    return _PRICES is not None
