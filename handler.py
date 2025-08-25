#!/usr/bin/env python3
# handler.py
"""
批量并行调用 `myth a -o json --bin-runtime -f <hex_file>`
使用全部逻辑核心，并记录每个任务的用时与输出。

依赖:
  - Python ≥ 3.8
  - mythril 或其它提供 `myth` 可执行文件的工具

用法:
  python handler.py /path/to/hex_dir
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from pathlib import Path
from typing import Dict, List

# -------- 命令行解析 ----------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="并行 myth 分析脚本")
    p.add_argument(
        "directory",
        type=Path,
        help="包含 *.hex 文件的目标目录",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("outputs"),
        help="存放分析结果 JSON 的目录 (默认: ./outputs)",
    )
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="并行进程数 (默认=CPU 逻辑核心数)",
    )
    return p.parse_args()


# -------- 单个任务的执行函数 --------------------------------------------------


def run_myth(hex_path: Path, output_dir: Path) -> Dict:
    """
    调用 myth 工具分析单个 .hex 文件。
    返回包含统计信息的字典。
    """
    start = time.perf_counter()

    cmd = [
        "myth",
        "a",
        "-m",
        "AccidentallyKillable",
        "-o",
        "json",
        "--bin-runtime",
        "-f",
        str(hex_path),
    ]

    log_file = Path(f"{hex_path}.log")
    out_file = output_dir / f"{hex_path.stem}.json"
    
    with open(log_file, 'w', encoding='utf-8') as log_f:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,  # 捕获stdout用于保存JSON
            stderr=log_f,           # stderr直接写入日志文件
            text=True,
        )

    elapsed = time.perf_counter() - start

    # 保存JSON输出
    try:
        out_file.write_text(proc.stdout, encoding="utf-8")
    except Exception as e:
        # 追加写文件失败信息到日志
        with open(log_file, 'a', encoding='utf-8') as log_f:
            log_f.write(f"\n\n[handler.py] 保存输出失败: {e}")

    return {
        "file": str(hex_path),
        "seconds": round(elapsed, 3),
        "returncode": proc.returncode,
        "stdout_bytes": len(proc.stdout.encode("utf-8")),
        "stderr_bytes": log_file.stat().st_size if log_file.exists() else 0,
        "output_path": str(out_file),
        "log_path": str(log_file),
    }


# -------- 主流程 --------------------------------------------------------------


def main() -> None:
    args = parse_args()

    target_dir: Path = args.directory.expanduser().resolve()
    output_dir: Path = args.output.expanduser().resolve()
    jobs: int = max(1, args.jobs)

    if not target_dir.is_dir():
        sys.exit(f"目标目录不存在: {target_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    hex_files: List[Path] = sorted(target_dir.glob("*.hex"))
    if not hex_files:
        sys.exit("目标目录下未找到 *.hex 文件")

    print(
        f"将使用 {jobs} 个并行进程分析 {len(hex_files)} 个 .hex 文件 …\n"
        f"结果 JSON 将写入: {output_dir}\n"
    )

    # 捕获 Ctrl-C，优雅退出
    original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        signal.signal(signal.SIGINT, original_sigint_handler)  # 还原
        future_map = {executor.submit(run_myth, p, output_dir): p for p in hex_files}

        results: List[Dict] = []
        try:
            for fut in as_completed(future_map):
                path = future_map[fut]
                try:
                    res = fut.result()
                    results.append(res)
                    print(
                        f"[✓] {Path(res['file']).name:<30} "
                        f"{res['seconds']:>6.2f}s  rc={res['returncode']}"
                    )
                except Exception as exc:
                    print(f"[✗] {path.name}  执行异常: {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\n用户终止，正在取消剩余任务 …", file=sys.stderr)
            for f in future_map:
                f.cancel()
            executor.shutdown(cancel_futures=True)
            sys.exit(130)

    # 写汇总文件
    summary_path = output_dir / "run_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n全部完成，汇总已写入: {summary_path}")


if __name__ == "__main__":
    main()
