"""Interest-free RUB schedules; all allocation is in integer kopecks."""

from __future__ import annotations

import calendar
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


_MONEY = re.compile(r"[0-9]{1,12}(?:[.,][0-9]{1,2})?\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _money_kopecks(value: str, field: str) -> int:
    if not isinstance(value, str) or not _MONEY.fullmatch(value.strip()):
        raise ValueError(f"{field}: нужна сумма от 0 до 999999999999.99 с максимум двумя знаками после запятой")
    return int(Decimal(value.strip().replace(",", ".")) * 100)


def _rub(kopecks: int) -> str:
    whole, fraction = divmod(kopecks, 100)
    return f"{whole}.{fraction:02d}"


def _iso_date(value: str, field: str) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError(f"{field}: нужна дата в формате YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field}: недопустимая календарная дата") from error


def build_schedule(price: str, down_payment: str, months: int, start_date: str) -> dict:
    """Return day-zero payment plus 1..360 monthly payments without interest.

    Full ruble inputs are strings. More than two decimal places are rejected,
    never rounded. Each regular payment is the whole-kopeck quotient; any
    remaining kopecks are added only to the final payment. Dates are anchored
    to the original day, clamped independently in each destination month.
    """
    total = _money_kopecks(price, "price")
    initial = _money_kopecks(down_payment, "down_payment")
    if total <= 0 or initial >= total:
        raise ValueError("Цена должна быть положительной; первоначальный взнос должен быть меньше цены")
    if type(months) is not int or not 1 <= months <= 360:
        raise ValueError("months: нужно целое число от 1 до 360")
    remaining = total - initial
    if remaining < months:
        raise ValueError("Остаток должен позволять платеж не меньше одной копейки в каждый месяц")
    start = _iso_date(start_date, "start_date")
    final_year = (start.year * 12 + start.month - 1 + months) // 12
    if final_year > 9999:
        raise ValueError("График выходит за пределы допустимого календаря")

    rows = [{"number": 0, "date": start.isoformat(), "amount": _rub(initial), "balance": _rub(remaining)}]
    regular, remainder = divmod(remaining, months)
    for number in range(1, months + 1):
        year, zero_month = divmod(start.year * 12 + start.month - 1 + number, 12)
        month = zero_month + 1
        due = date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
        payment = regular + (remainder if number == months else 0)
        remaining -= payment
        rows.append({"number": number, "date": due.isoformat(), "amount": _rub(payment), "balance": _rub(remaining)})
    return {"price": _rub(total), "down_payment": _rub(initial), "months": months,
            "start_date": start.isoformat(), "rows": rows}


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold_ics(line: str) -> str:
    """RFC 5545 folding counts UTF-8 octets, including continuation spaces."""
    parts = []
    current = ""
    octets = 0
    for character in line:
        size = len(character.encode("utf-8"))
        if octets + size > 75:
            parts.append(current)
            current, octets = " ", 1
        current += character
        octets += size
    parts.append(current)
    return "\r\n".join(parts)


def export_schedule(schedule: dict, directory: Path) -> list[Path]:
    """Write UTF-8 CSV and all-day ICS files; do not send or import a calendar.

    The calendar contains no alarms or attendees. Stable UIDs help calendar
    applications recognize a repeat import of the same calculation.
    """
    if not isinstance(schedule, dict):
        raise ValueError("Нужен график, полученный через build_schedule")
    try:
        canonical = build_schedule(schedule["price"], schedule["down_payment"],
                                   schedule["months"], schedule["start_date"])
    except (KeyError, TypeError) as error:
        raise ValueError("Неполный график") from error
    if schedule != canonical:
        raise ValueError("Платежи или параметры графика изменены; пересчитайте график")

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "schedule.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["number", "date", "amount", "balance"])
        writer.writeheader()
        writer.writerows(canonical["rows"])

    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:24]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SKIF//Installments 1.0//RU", "CALSCALE:GREGORIAN"]
    for row in canonical["rows"]:
        label = "Первоначальный взнос" if row["number"] == 0 else f"Платеж {row['number']}"
        description = (f"Предварительный расчет без процентов. Сумма {row['amount']} RUB; "
                       f"остаток {row['balance']} RUB. Сроки требуют согласования в договоре. "
                       "Запись календаря не подтверждает оплату.")
        lines.extend(["BEGIN:VEVENT", f"UID:{digest}-{row['number']}@skif.local", f"DTSTAMP:{stamp}",
                      "DTSTART;VALUE=DATE:" + row["date"].replace("-", ""), "DURATION:P1D",
                      "SUMMARY:" + _ics_text(f"{label} — {row['amount']} RUB"),
                      "DESCRIPTION:" + _ics_text(description), "TRANSP:TRANSPARENT", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    ics_path = directory / "schedule.ics"
    ics_path.write_bytes(("\r\n".join(_fold_ics(line) for line in lines) + "\r\n").encode("utf-8"))
    return [csv_path, ics_path]
