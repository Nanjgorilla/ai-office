M = (1 << 64) - 1
RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
      0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
      0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
      0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
      0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
      0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
       [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]


def rol(v, n):
    return ((v << n) | (v >> (64 - n))) & M if n else v


def keccak_f(A):
    for rnd in range(24):
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                A[x][y] ^= D[x]
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                B[y][(2 * x + 3 * y) % 5] = rol(A[x][y], ROT[x][y])
        for x in range(5):
            for y in range(5):
                A[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y] & M) & B[(x + 2) % 5][y])
        A[0][0] ^= RC[rnd]
    return A


def keccak256(data: bytes) -> bytes:
    rate = 136
    pad = rate - len(data) % rate
    data = data + (b"\x01" + b"\x00" * (pad - 2) + b"\x80" if pad > 1 else b"\x81")
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(data), rate):
        blk = data[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(blk[i * 8:i * 8 + 8], "little")
            A[i % 5][i // 5] ^= lane
        keccak_f(A)
    out = b""
    for i in range(4):
        out += A[i % 5][i // 5].to_bytes(8, "little")
    return out


assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
assert keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"


def to_checksum(addr: str) -> str:
    low = addr.lower().replace("0x", "")
    h = keccak256(low.encode()).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(low))


if __name__ == "__main__":
    import sys
    given = sys.argv[1]
    body = given[2:] if given.lower().startswith("0x") else given
    print(f"入力          : {given}")
    print(f"長さ          : 0x + {len(body)}文字 ({'正しい' if len(body) == 40 else '異常: 40文字であるべき'})")
    print(f"16進数として   : {'正しい' if all(c in '0123456789abcdefABCDEF' for c in body) else '異常'}")
    correct = to_checksum(body)
    mixed = body != body.lower() and body != body.upper()
    print(f"正しい表記     : {correct}")
    if not mixed:
        print("判定          : 大文字小文字が混ざっていないため、検算できない")
    elif correct.lower() == given.lower() and correct == ("0x" + body if not given.lower().startswith("0x") else given):
        print("判定          : ✅ 検算を通過（打ち間違いなし）")
    else:
        print("判定          : ❌ 検算に失敗。打ち間違いの可能性がある")
