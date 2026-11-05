"""Выдать продуктовый код и записать его HMAC-хеш в data/product_codes.txt.

Запуск из корня проекта:
  .venv\\Scripts\\python scripts/issue_code.py
  .venv\\Scripts\\python scripts/issue_code.py --count 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth import CODES_FILE, append_hash, generate_code  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Выдать продуктовый код")
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()
    print(f"Хеши пишутся в {CODES_FILE}")
    print("Отправь код пользователю на почту. В файл попадает только хеш.")
    for _ in range(max(1, args.count)):
        code = generate_code()
        append_hash(code)
        print(code)


if __name__ == "__main__":
    main()
