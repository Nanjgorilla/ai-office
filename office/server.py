#!/usr/bin/env python3
"""バーチャルオフィスを見るための小さな配信係。

平面図は `office/activity.jsonl` を1秒ごとに読みに行くが、
ファイルを直接開いた（file:// で開いた）場合は、その読み込みが
ブラウザに止められる。そのときはデモ運転になる。

実際の動きを見たいときは、これを走らせてから
http://localhost:8765/ を開く。

    python3 office/server.py            # 8765番で開く
    python3 office/server.py 9000       # 番号を変える

止めるときは Ctrl+C。
"""

import http.server
import socketserver
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    """office/ の中だけを配る。記録は毎回読み直させる。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        # 記録は増え続けるので、ブラウザに溜め込ませない
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        # 1秒ごとの読み込みで画面が埋まるので、黙らせる
        pass


def main() -> int:
    port = 8765
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"番号として読めません: {sys.argv[1]}")
            return 1

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
            print(f"バーチャルオフィスを開きました → http://localhost:{port}/")
            print("止めるときは Ctrl+C")
            httpd.serve_forever()
    except OSError as e:
        print(f"{port}番が使えません（{e}）。別の番号を渡してください。")
        return 1
    except KeyboardInterrupt:
        print("\n閉じました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
