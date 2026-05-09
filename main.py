#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=================================================================
  MICRO DESK OS  /  ASM MODE
  Version 1.0  --  Python Assembler-Style CLI Terminal
=================================================================
  アセンブラ風コマンドで動くレトロ端末シミュレータ
  ブログサンプル用Pythonスクリプト
=================================================================
"""

import math
import os
import time
import unicodedata
import webbrowser
import datetime
import sys

# Windows環境でUTF-8出力に統一する（文字化け対策）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# -----------------------------------------------------------------
# ANSIカラー定数
# 黒背景＋緑文字のCRT風スタイル
# -----------------------------------------------------------------
GREEN      = "\033[92m"    # 明るい緑（メインテキスト）
DIM_GREEN  = "\033[32m"    # 暗い緑（罫線・装飾など）
BOLD_GREEN = "\033[1;92m"  # 太字の明るい緑（タイトル強調）
BLACK_BG   = "\033[40m"    # 黒背景
RESET      = "\033[0m"     # 全属性リセット
CLEAR      = "\033[2J\033[H"  # 画面クリア＋カーソルを左上へ

# -----------------------------------------------------------------
# データストア
# ここをJSONファイルの読み書きに差し替えれば永続化できる
# 例: import json / json.load() / json.dump() で置き換えるだけ
# -----------------------------------------------------------------
REGISTERS = {
    "TODO": [],   # TODOリスト（文字列のリスト）
    "MEMO": [],   # メモリスト（文字列のリスト）
    "ACC":  0,    # アキュムレータ：直近のCALC結果を保持
}

# よく使うURLブックマーク
URL_BOOK = {
    "GOOGLE":  "https://www.google.com",
    "GITHUB":  "https://github.com",
    "PYPI":    "https://pypi.org",
    "BLOG":    "https://your-blog.example.com",
}

# 画面幅（文字数）
WIDTH = 62

# =================================================================
# ターミナルスタイル制御
# =================================================================

def enable_terminal_style():
    """
    黒背景＋緑文字のCRT風スタイルを有効にする。
    os.system("color") を呼ぶと Windows のコンソールで
    ANSI エスケープシーケンスが有効になる（Win10以降）。
    画面クリア後、以降の出力を緑文字に固定する。
    """
    os.system("color")          # WindowsでANSIを有効化（他OSでは無害）
    print(CLEAR, end="")        # 画面クリア
    print(BLACK_BG + GREEN, end="", flush=True)   # 黒背景＋緑文字に設定

def boot_sleep(sec: float = 0.04):
    """TTY（実ターミナル）のときだけスリープする。パイプ入力時はスキップ。"""
    if sys.stdin.isatty():
        time.sleep(sec)

def boot_blink_cursor(duration: float = 3.0, interval: float = 0.45):
    """
    ブート演出用のブロックカーソル点滅。
    duration 秒間、interval 秒ごとに █ と空白を交互に表示する。
    パイプ入力時はスキップ（TTYのみ実行）。
    """
    if not sys.stdin.isatty():
        return
    cycles = int(duration / interval)
    for i in range(cycles):
        ch = "█" if i % 2 == 0 else " "
        print(f"\r  {ch}", end="", flush=True)
        time.sleep(interval)
    print("\r   ", end="", flush=True)  # 最後は空白で消してから改行
    print()

def boot_diagnostics():
    """
    MZ-80K風の起動診断シーケンスを表示する。
    MEMORY R/W TEST は \\r で同じ行を上書きしてアドレスが
    カウントアップして見えるようにする（最終行だけ残す）。
    """
    boot_blink_cursor(duration=3.0, interval=0.45)   # タイトル表示前に点滅
    print("  **** MICRO DESK OS BOOT MONITOR ****")
    print()

    # -- MEMORY R/W TEST ------------------------------------------
    print("  MEMORY R/W TEST")

    checksum = 0
    for i, addr in enumerate(range(0x0000, 0x2000, 0x0100)):
        pattern    = 0x55 if i % 2 == 0 else 0xAA
        read_value = pattern                           # 疑似リード（常に一致）
        checksum   = (checksum + addr + pattern) & 0xFFFF

        line = f"  ADDR {addr:04X}  W:{pattern:02X}  R:{read_value:02X}  OK"
        print("\r" + line, end="", flush=True)         # 同じ行を上書き
        boot_sleep(0.08)

    print()   # メモリテスト完了後だけ改行して最終アドレス行を確定させる
    print(f"  MEMORY CHECKSUM  {checksum:04X}  OK")
    print()

    # -- I/O CHECK ------------------------------------------------
    print("  I/O CHECK")
    boot_sleep(0.20)
    for name in ["KEYBOARD", "DISPLAY", "URL PORT", "FILE BUS"]:
        print(f"  {name:<10} OK")
        boot_sleep(0.25)

    print()
    boot_sleep(0.30)
    print("  LOADING ASM MONITOR ...")
    boot_sleep(1.20)                 # ← ここで溜める
    print("  MONITOR READY.")
    boot_sleep(0.60)
    print("  OK")
    print()

def reboot_system():
    """
    REBOOT / RST コマンドの処理。
    画面クリア→診断→ヘッダー再表示を行い、入力ループには戻る。
    REGISTERS のデータは消去しない（疑似OSとしてメモリ保持扱い）。
    """
    print()
    print("  REBOOT REQUESTED ...")
    boot_sleep(0.30)
    enable_terminal_style()
    boot_diagnostics()
    print_boot_header()

def read_command() -> str:
    """コマンド入力を受け付ける"""
    return input("  ASM> ")

# =================================================================
# 表示ユーティリティ
# =================================================================

def display_width(text: str) -> int:
    """
    文字列の表示幅を返す。
    全角文字（W/F/Aカテゴリ）は 2、それ以外は 1 として数える。
    len() の代わりにこれを使うことで日本語混在時もズレない。
    """
    w = 0
    for ch in str(text):
        if unicodedata.east_asian_width(ch) in ("F", "W", "A"):
            w += 2
        else:
            w += 1
    return w

def pad_display(text: str, width: int) -> str:
    """
    text を表示幅 width になるようにスペースで右埋めして返す。
    はみ出す場合はそのまま返す（呼び出し側でトリム済み前提）。
    """
    text = str(text)
    padding = width - display_width(text)
    return text + " " * max(padding, 0)

def divider(char="-"):
    """水平線を返す（デフォルトはハイフン）"""
    return char * WIDTH

def center_text(text):
    """テキストを中央揃えして返す"""
    return text.center(WIDTH)

def print_boot_header():
    """起動時のヘッダーを表示する（レトロ緑画面風）"""
    now = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    # 罫線は暗い緑、タイトルは太字の明るい緑で濃淡をつける
    print()
    print(DIM_GREEN  + divider("=") + GREEN)
    print(BOLD_GREEN + center_text("MICRO DESK OS  /  ASM MODE") + GREEN)
    print(DIM_GREEN  + center_text(f"v1.0   [{now}]") + GREEN)
    print(DIM_GREEN  + divider("=") + GREEN)
    print("  >> SYSTEM READY.  TYPE [HELP] FOR COMMAND LIST.")
    print(DIM_GREEN  + divider() + GREEN)
    print()

def sys_msg(tag, msg):
    """タグ付きのシステムメッセージを表示する"""
    print(f"  [{tag}] {msg}")

def sys_ok(msg):
    """成功メッセージ：8ビット機風の "OK / 内容" 形式"""
    print("  OK")
    print(f"    {msg}")

def sys_err(msg):
    """エラーメッセージ：8ビット機風の "?SYNTAX ERROR" 形式"""
    print(f"  ?{msg}")

def sys_inf(msg):
    """補足情報メッセージ"""
    print(f"    {msg}")

def print_table(rows, title="DATA"):
    """
    ボックス付きテーブルを表示する。
    rows : 表示する文字列のリスト
    title: ボックスのタイトル

    寸法（全行が WIDTH 文字になるよう統一）:
      "  |  " (5) + inner (WIDTH-6) + "|" (1) = WIDTH
      "  +"   (3) + WIDTH-4 dashes  + "+" (1) = WIDTH
    """
    inner  = WIDTH - 6    # 本文の有効表示幅（display_width 基準）
    hline  = WIDTH - 4    # 上下枠線の内側ダッシュ数

    # タイトル付き上枠: "  +-- TITLE ---...+"
    title_dashes = hline - 3 - display_width(title) - 1  # "-- "(3) + title + " "(1)
    top    = "  +-- " + title + " " + "-" * max(title_dashes, 0) + "+"
    bottom = "  +" + "-" * hline + "+"

    print(top)
    if rows:
        for i, row in enumerate(rows):
            line = f"[{i:02d}] {row}"
            # 表示幅超えは末尾を省略
            while display_width(line) > inner:
                line = line[:-1]
            if display_width(f"[{i:02d}] {row}") > inner:
                line = line[:-3] + "..."
            print(f"  |  {pad_display(line, inner)}|")
    else:
        print(f"  |  {pad_display('(EMPTY)', inner)}|")
    print(bottom)
    print()

# =================================================================
# 安全な電卓
# eval を使うが __builtins__ を空にし、math 関数のみ許可する
# =================================================================

# 許可する関数・定数（math モジュールの公開メンバーのみ）
_SAFE_NAMESPACE = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_SAFE_NAMESPACE["abs"]   = abs
_SAFE_NAMESPACE["round"] = round

# 入力に含んでよい文字のセット（英数字・演算子・空白のみ）
_ALLOWED_CHARS = set(
    "0123456789 +-*/.()%_"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)

def safe_eval(expr: str):
    """
    制限付き eval で数式を評価する。
    - __builtins__ を空辞書に差し替えて組み込み関数を封じる
    - 許可リストにない文字が含まれていたら ValueError を投げる
    - 戻り値: 計算結果（数値）
    """
    if not all(c in _ALLOWED_CHARS for c in expr):
        raise ValueError("Illegal character in expression")
    # 第2引数に {"__builtins__": {}} を渡すことで import や exec を防ぐ
    result = eval(expr, {"__builtins__": {}}, _SAFE_NAMESPACE)
    return result

# =================================================================
# 各コマンドの実装
# =================================================================

def cmd_help():
    """HELP: コマンド一覧を表示する"""
    cmds = [
        ("LDA TODO",         "Show TODO list"),
        ("STA TODO <text>",  "Add item to TODO"),
        ("DEL TODO <no>",    "Delete TODO by index"),
        ("LDA MEMO",         "Show MEMO list"),
        ("STA MEMO <text>",  "Add item to MEMO"),
        ("DEL MEMO <no>",    "Delete MEMO by index"),
        ("CALC <expr>",      "Calculator  e.g. CALC 1200 * 3"),
        ("CALL URL <name>",  "Open bookmark URL in browser"),
        ("CALL URLS",        "Show URL bookmark list"),
        ("PRT <text>",       "Print text to screen"),
        ("NOP",              "No operation"),
        ("CLS",              "Clear screen"),
        ("REBOOT / RST",     "Reboot monitor"),
        ("HLT",              "Halt / Exit"),
    ]
    col1   = 22           # コマンド列の表示幅
    hline  = WIDTH - 4    # 枠線の内側文字数: "  +"(3) + hline + "+"(1) = WIDTH
    inner  = WIDTH - 6    # 本文の有効表示幅: "  | "(4) + inner + " |"(2) = WIDTH

    print()
    print(f"  +{'=' * hline}+")
    # タイトルを display_width 基準で中央揃え
    title_str = "COMMAND REFERENCE"
    side = (hline - display_width(title_str)) // 2
    print(f"  |{' ' * side}{title_str}{' ' * (hline - side - display_width(title_str))}|")
    print(f"  +{'=' * hline}+")
    for cmd, desc in cmds:
        line = f"  {cmd:<{col1}} {desc}"
        # 表示幅超えは末尾を省略
        while display_width(line) > inner:
            line = line[:-1]
        print(f"  | {pad_display(line, inner)} |")
    print(f"  +{'=' * hline}+")
    print()

def cmd_lda(arg: str):
    """
    LDA (Load): レジスタの内容を読み込んで表示する。
    アセンブラの LDA 命令（メモリ→アキュムレータへのロード）に対応。
    """
    if arg in ("TODO", "MEMO"):
        print_table(REGISTERS[arg], title=f"{arg} LIST")
    else:
        sys_err(f"Unknown register: {arg}  (TODO / MEMO)")

def cmd_sta(arg: str, value: str):
    """
    STA (Store): レジスタにデータを書き込む。
    アセンブラの STA 命令（アキュムレータ→メモリへのストア）に対応。
    """
    if arg not in ("TODO", "MEMO"):
        sys_err(f"Unknown register: {arg}  (TODO / MEMO)")
        return
    if not value:
        sys_err(f"No value given.  Example: STA {arg} Buy milk")
        return
    REGISTERS[arg].append(value)
    idx = len(REGISTERS[arg]) - 1
    sys_ok(f"STORED {arg}[{idx:02d}] : {value}")

def cmd_del(arg: str, idx_str: str):
    """
    DEL: レジスタから指定インデックスの要素を削除する。
    """
    if arg not in ("TODO", "MEMO"):
        sys_err(f"Unknown register: {arg}  (TODO / MEMO)")
        return
    if not idx_str.isdigit():
        sys_err(f"Index must be a number.  Example: DEL {arg} 0")
        return
    idx = int(idx_str)
    data = REGISTERS[arg]
    if not (0 <= idx < len(data)):
        sys_err(f"Index {idx} out of range (0 - {len(data) - 1})")
        return
    removed = data.pop(idx)
    sys_ok(f"DELETED {arg}[{idx:02d}] : {removed}")

def cmd_calc(expr: str):
    """
    CALC: 安全な電卓。計算結果を ACC レジスタにも保存する。
    """
    if not expr:
        sys_err("No expression given.  Example: CALC 1200 * 3")
        return
    try:
        result = safe_eval(expr)
        REGISTERS["ACC"] = result   # アキュムレータに保存
        sys_ok(f"{expr}  =  {result}")
    except ZeroDivisionError:
        sys_err("Division by zero")
    except (SyntaxError, NameError, ValueError) as e:
        sys_err(f"Calc error: {e}")

def cmd_call(arg: str, rest: str):
    """
    CALL: サブルーチン（URL）を呼び出す。
    - CALL URL <name> ... ブックマークURLをブラウザで開く
    - CALL URLS       ... ブックマーク一覧を表示
    """
    if arg == "URLS":
        # URLブックマーク一覧を表示
        rows = [f"{k:<12} -> {v}" for k, v in URL_BOOK.items()]
        print_table(rows, title="URL BOOKMARKS")

    elif arg == "URL":
        name = rest.upper().strip()
        if not name:
            sys_err("No URL name given.  Example: CALL URL GITHUB")
            sys_inf("Available: " + "  /  ".join(URL_BOOK.keys()))
            return
        if name not in URL_BOOK:
            sys_err(f"'{name}' is not in bookmarks")
            sys_inf("Available: " + "  /  ".join(URL_BOOK.keys()))
            return
        url = URL_BOOK[name]
        sys_ok(f"OPENING : {url}")
        webbrowser.open(url)

    else:
        sys_err(f"Unknown CALL target: {arg}")
        sys_inf("Usage: CALL URL <name>  or  CALL URLS")

def cmd_prt(text: str):
    """PRT: テキストをそのまま出力する"""
    if text:
        print(f"\n  >> {text}\n")
    else:
        print()

def cmd_nop():
    """NOP (No Operation): 何もしない。ウォームアップや区切りに使う"""
    sys_msg("NOP", "no operation.")

# =================================================================
# コマンドパーサ & ディスパッチャ
# 入力1行を受け取り、対応するコマンド関数を呼び出す
# =================================================================

def dispatch(line: str) -> bool:
    """
    1行を解析してコマンドを実行する。
    戻り値: True=継続 / False=終了（HLT 命令時）
    """
    line = line.strip()

    # 空行・コメント行（; で始まる）はスキップ
    if not line or line.startswith(";"):
        return True

    # 最大3つに分割: [オペコード, 第1オペランド, 残りの文字列]
    parts = line.split(None, 2)
    opcode = parts[0].upper()

    # ---- HLT ------------------------------------------------
    if opcode == "HLT":
        print()
        print(DIM_GREEN + divider("=") + GREEN)
        sys_msg("SYS", "SYSTEM HALTED.  GOODBYE.")
        print(DIM_GREEN + divider("=") + RESET)   # 終了時にターミナル色をリセット
        print()
        return False   # False でメインループを終了させる

    # ---- HELP -----------------------------------------------
    elif opcode == "HELP":
        cmd_help()

    # ---- LDA reg --------------------------------------------
    elif opcode == "LDA":
        arg = parts[1].upper() if len(parts) > 1 else ""
        cmd_lda(arg)

    # ---- STA reg [value] ------------------------------------
    elif opcode == "STA":
        arg   = parts[1].upper() if len(parts) > 1 else ""
        value = parts[2]         if len(parts) > 2 else ""
        cmd_sta(arg, value)

    # ---- DEL reg index --------------------------------------
    elif opcode == "DEL":
        arg     = parts[1].upper() if len(parts) > 1 else ""
        idx_str = parts[2]         if len(parts) > 2 else ""
        cmd_del(arg, idx_str)

    # ---- CALC expression ------------------------------------
    elif opcode == "CALC":
        expr = " ".join(parts[1:]) if len(parts) > 1 else ""
        cmd_calc(expr)

    # ---- CALL target [arg] ----------------------------------
    elif opcode == "CALL":
        arg  = parts[1].upper() if len(parts) > 1 else ""
        rest = parts[2]         if len(parts) > 2 else ""
        cmd_call(arg, rest)

    # ---- PRT [text] -----------------------------------------
    elif opcode == "PRT":
        text = " ".join(parts[1:]) if len(parts) > 1 else ""
        cmd_prt(text)

    # ---- NOP ------------------------------------------------
    elif opcode == "NOP":
        cmd_nop()

    # ---- REBOOT / RST ---------------------------------------
    elif opcode in ("REBOOT", "RST"):
        reboot_system()

    # ---- CLS ------------------------------------------------
    elif opcode == "CLS":
        print(CLEAR, end="", flush=True)

    # ---- 未定義命令 -----------------------------------------
    else:
        sys_err(f"ILLEGAL OPCODE")
        sys_inf(f"OPCODE : {opcode}")
        sys_inf("TYPE HELP FOR COMMAND LIST")

    return True   # True で継続

# =================================================================
# メインループ
# =================================================================

def main():
    enable_terminal_style()   # 黒背景＋緑文字を有効化してから描画
    boot_diagnostics()
    print_boot_header()

    while True:
        try:
            raw = read_command()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+D / Ctrl+C による割り込みでも正常終了
            print()
            print()
            sys_msg("INT", "INTERRUPTED.  SYSTEM HALTED.")
            print(RESET)   # 終了時にターミナル色をリセット
            break

        # dispatch() が False を返したら（HLT 命令）ループを抜ける
        if not dispatch(raw):
            break


if __name__ == "__main__":
    main()
