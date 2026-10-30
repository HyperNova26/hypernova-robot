#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
"""Create only an empty dated output directory; scene decomposition is unimplemented."""

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]


def nonempty_path(value):
    if not value:
        raise argparse.ArgumentTypeError("path must be nonempty")
    return Path(value)


def parse_args():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "INPUT 파일을 확인하고 날짜별 빈 결과 폴더를 만듭니다. "
            "미구현 (not implemented): ground/cars/other 분해는 수행하지 않습니다."
        ),
        epilog="생성한 폴더는 비어 있으며 분류 파일이나 완료 표시를 만들지 않습니다.",
    )
    parser.add_argument("input", type=nonempty_path, metavar="INPUT")
    parser.add_argument(
        "--date",
        metavar="MMDD",
        default=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m%d"),
        help="folder date (default: today's date in Asia/Seoul)",
    )
    parser.add_argument(
        "--output-root",
        type=nonempty_path,
        metavar="DIR",
        default=ROOT / "sim_scenes",
        help="parent folder (default: <repository>/sim_scenes)",
    )
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9]{4}", args.date):
            raise ValueError
        # MMDD has no year: retain February 29 as a valid folder date.
        date(2000, int(args.date[:2]), int(args.date[2:]))
    except ValueError:
        parser.error("--date must be a valid MMDD")
    return args


def main():
    args = parse_args()
    try:
        if not args.input.is_file() or not os.access(args.input, os.R_OK):
            raise ValueError(f"INPUT must be a readable file: {args.input}")
        # Confirm readability without parsing or modifying the source.
        with args.input.open("rb"):
            pass
        args.output_root.mkdir(parents=True, exist_ok=True)
        output_path = args.output_root.resolve() / f"{args.date}_demo_disassembled"
        # Atomic mkdir rejects existing files, empty folders, and dangling symlinks.
        output_path.mkdir()
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("미구현 (not implemented): ground/cars/other 분해는 수행하지 않았습니다.")
    print(f"빈 폴더만 생성했습니다: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
