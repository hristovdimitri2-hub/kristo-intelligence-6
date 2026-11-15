"""Проверка на private key срещу payTo адреса.

Чете ключа от stdin (не от аргументи — иначе се вижда в списъка с процеси),
извежда адреса и казва дали е търсеният. Нищо не се записва на диск.

    echo 0x.... | python check_key.py
"""

import sys

TARGET = "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f"

#: ASCII tokens only. The caller renders the human label: a Cyrillic string
#: returned over a captured pipe is decoded with the console codepage and comes
#: out as mojibake, which is exactly the kind of wrong-looking output that would
#: make the owner doubt a correct answer.
KNOWN = {
    "0xe50c5212e8211639c49276da190e248b83935763": "DEMO",
    "0x9c1eb97e121a6836200c539a1bf0ecdc37f750dd": "GAS",
    "0xd4cda980839c8fed4374ee37ea8dbe8c4ecfd88f": "OLD_WRONG",
    "0x0e12875930795b83cd5e25570a56de8a703eeb66": "ANCHOR",
}


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("EMPTY")
        return 1

    key = raw if raw.startswith("0x") else "0x" + raw

    try:
        from eth_account import Account
    except Exception as exc:  # noqa: BLE001
        print("NO_LIB|%s" % type(exc).__name__)
        return 1

    try:
        address = Account.from_key(key).address
    except Exception as exc:  # noqa: BLE001
        print("INVALID|%s" % type(exc).__name__)
        return 1

    print("ADDR|%s" % address)
    low = address.lower()
    if low == TARGET:
        print("RESULT|MATCH")
        return 0
    print("RESULT|KNOWN|%s" % KNOWN.get(low, ""))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
