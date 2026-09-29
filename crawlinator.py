#!/usr/bin/env python3
"""Inspect filesystem sizes and find fully inspected, stale subdirectories."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import heapq
import json
import os
import pprint
import re
import stat
import sys
import tempfile
import time
import tracemalloc
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Sequence

SECONDS_PER_DAY = 86_400
TIME_NAMES = {"a": "access", "m": "modification", "c": "metadata change"}
SIZE_UNITS = ("Bytes", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")


@dataclass(frozen=True)
class ScanOptions:
    days_old: int | None = None
    use_time: str = "m"
    top_file_count: int | None = None
    size_histogram: bool = False
    exclusions: tuple[str, ...] = ()
    workers: int = 1

    def __post_init__(self):
        for name in ("days_old", "top_file_count"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise ValueError(f"{name} must be a positive integer")
        if self.use_time not in TIME_NAMES:
            raise ValueError("use_time must be 'a', 'm', or 'c'")
        if not isinstance(self.workers, int) or self.workers <= 0:
            raise ValueError("workers must be a positive integer")


@dataclass
class DirectorySummary:
    complete: bool = True
    newest_time: float | None = None

    def include_time(self, timestamp: float):
        if self.newest_time is None or timestamp > self.newest_time:
            self.newest_time = timestamp

    def include_child(self, child: DirectorySummary):
        self.complete = self.complete and child.complete
        if child.newest_time is not None:
            self.include_time(child.newest_time)

    def status(self, cutoff: float) -> str:
        if not self.complete:
            return "unknown"
        if self.newest_time is None:
            return "empty"
        return "stale" if self.newest_time <= cutoff else "active"


@dataclass
class DirectoryFrame:
    path: str
    parent: DirectoryFrame | None = None
    summary: DirectorySummary = field(default_factory=DirectorySummary)
    remaining_children: int = 0


class FilesystemStats:
    """Aggregate inspected files without retaining every file's metadata."""

    def __init__(self):
        self.stats = {
            "TotalFiles": 0,
            "TotalSize": 0,
            "TotalDirs": 0,
            "DiscoveredEntries": 0,
            "OldestFile": {"Path": None, "Age": None},
            "NewestFile": {"Path": None, "Age": None},
            "Failures": [],
            "FailureCount": 0,
            "SkippedEntries": {"Excluded": 0, "Symlinks": 0, "SpecialFiles": 0},
            "LargestFiles": [],
            "ScanComplete": True,
            "ExecutionTime": None,
        }
        self._largest: list[tuple[int, str]] = []
        self._histogram: dict[int, int] = {}

    def record_failure(self, path: str, operation: str, error: OSError):
        self.stats["Failures"].append(
            {
                "Path": path,
                "Operation": operation,
                "Error": str(error),
                "Errno": error.errno,
            }
        )
        self.stats["FailureCount"] += 1

    def record_timestamp(self, path: str, timestamp: float):
        # Tie-break by path so completion order never changes the report.
        for key, older in (("OldestFile", True), ("NewestFile", False)):
            current = self.stats[key]["Age"]
            if (
                current is None
                or (timestamp < current if older else timestamp > current)
                or (timestamp == current and path < self.stats[key]["Path"])
            ):
                self.stats[key] = {"Path": path, "Age": timestamp}

    def record_size(self, item: tuple[int, str], limit: int):
        if len(self._largest) < limit:
            heapq.heappush(self._largest, item)
        else:
            heapq.heappushpop(self._largest, item)

    def record_file(self, path: str, info: os.stat_result, options: ScanOptions) -> float:
        timestamp = getattr(info, f"st_{options.use_time}time")
        self.stats["TotalFiles"] += 1
        self.stats["TotalSize"] += info.st_size
        self.record_timestamp(path, timestamp)
        if options.top_file_count is not None:
            self.record_size((info.st_size, path), options.top_file_count)
        if options.size_histogram:
            # Inclusive upper bounds, computed before any unit conversion.
            bound = max(1024, 1 << max(0, info.st_size - 1).bit_length())
            self._histogram[bound] = self._histogram.get(bound, 0) + 1
        return timestamp

    def merge(self, other: FilesystemStats, options: ScanOptions):
        """Merge one directory's private aggregates on the coordinator thread."""
        for key in ("TotalFiles", "TotalSize", "TotalDirs", "DiscoveredEntries", "FailureCount"):
            self.stats[key] += other.stats[key]
        self.stats["Failures"].extend(other.stats["Failures"])
        for key, count in other.stats["SkippedEntries"].items():
            self.stats["SkippedEntries"][key] += count
        for key in ("OldestFile", "NewestFile"):
            candidate = other.stats[key]
            if candidate["Age"] is not None:
                self.record_timestamp(candidate["Path"], candidate["Age"])
        if options.top_file_count is not None:
            # A directory's top N contains every entry that could enter the global top N.
            for item in other._largest:
                self.record_size(item, options.top_file_count)
        for bound, count in other._histogram.items():
            self._histogram[bound] = self._histogram.get(bound, 0) + count

    def finish(self, options: ScanOptions):
        self.stats["Failures"].sort(
            key=lambda item: (item["Path"], item["Operation"], item["Error"])
        )
        self.stats["LargestFiles"] = sorted(self._largest, key=lambda item: (-item[0], item[1]))
        if options.size_histogram:
            self.stats["SizeHistogram"] = {
                size_bucket_label(bound): count for bound, count in sorted(self._histogram.items())
            }


@dataclass
class DirectoryResult:
    summary: DirectorySummary = field(default_factory=DirectorySummary)
    children: list[str] = field(default_factory=list)
    stats: FilesystemStats = field(default_factory=FilesystemStats)


def is_link(info: os.stat_result) -> bool:
    """Also skip Windows junctions and other reparse points."""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def inspect_directory(path: str, options: ScanOptions, stopped: Event) -> DirectoryResult:
    """Read one directory into private aggregates; never wait for child jobs."""
    result = DirectoryResult()
    stats = result.stats
    summary = result.summary
    if stopped.is_set():
        summary.complete = False
        return result
    try:
        # Recheck queued directories in case they were replaced during the scan.
        info = os.lstat(path)
        if is_link(info):
            stats.stats["SkippedEntries"]["Symlinks"] += 1
            summary.complete = False
            return result
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(f"Directory changed during scan: {path}")
        with os.scandir(path) as entries:
            stats.stats["TotalDirs"] += 1
            for entry in entries:
                if stopped.is_set():
                    summary.complete = False
                    break
                stats.stats["DiscoveredEntries"] += 1
                if options.exclusions and any(
                    fnmatch.fnmatchcase(entry.name, pattern) for pattern in options.exclusions
                ):
                    stats.stats["SkippedEntries"]["Excluded"] += 1
                    summary.complete = False
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as error:
                    stats.record_failure(entry.path, "stat", error)
                    summary.complete = False
                    continue
                if is_link(info):
                    stats.stats["SkippedEntries"]["Symlinks"] += 1
                    summary.complete = False
                elif stat.S_ISDIR(info.st_mode):
                    result.children.append(entry.path)
                elif stat.S_ISREG(info.st_mode):
                    summary.include_time(stats.record_file(entry.path, info, options))
                else:
                    stats.stats["SkippedEntries"]["SpecialFiles"] += 1
                    summary.complete = False
    except OSError as error:
        stats.record_failure(path, "read directory", error)
        summary.complete = False
    return result


def scan_directories(root: DirectoryFrame, options: ScanOptions):
    """Yield completed directories, with at most `workers` submitted jobs."""
    ready = [root]
    pending = {}
    stopped = Event()
    executor = (
        ThreadPoolExecutor(max_workers=options.workers, thread_name_prefix="crawlinator")
        if options.workers > 1
        else None
    )
    try:
        while ready or pending:
            if executor is None:
                frame = ready.pop()
                completed = [(frame, inspect_directory(frame.path, options, stopped))]
            else:
                while ready and len(pending) < options.workers:
                    frame = ready.pop()
                    future = executor.submit(inspect_directory, frame.path, options, stopped)
                    pending[future] = frame
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                completed = [(pending.pop(future), future.result()) for future in done]
            for frame, result in completed:
                frame.summary = result.summary
                frame.remaining_children = len(result.children)
                ready.extend(DirectoryFrame(path=child, parent=frame) for child in result.children)
                yield frame, result.stats
    finally:
        stopped.set()
        if executor is not None:
            # Cancel queued work; active workers stop between filesystem operations.
            executor.shutdown(wait=True, cancel_futures=True)


def scan_filesystem(
    path: str | Path, options: ScanOptions | None = None, *, now: float | None = None
) -> dict:
    """Return a report. Rollups exclude the scan root and incomplete subtrees."""
    options = options if options is not None else ScanOptions()
    root = os.path.abspath(Path(path).expanduser())
    info = os.lstat(root)
    if is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"Scan path must be a directory, not a link: {root}")
    started = time.perf_counter()
    scan_time = time.time() if now is None else now
    cutoff = None
    if options.days_old is not None:
        try:
            cutoff = scan_time - options.days_old * SECONDS_PER_DAY
        except OverflowError:
            # No finite filesystem timestamp can be older than this threshold.
            cutoff = float("-inf")
    stats = FilesystemStats()
    root_frame = DirectoryFrame(root)
    candidates = []
    with closing(scan_directories(root_frame, options)) as directories:
        for frame, local_stats in directories:
            stats.merge(local_stats, options)
            # Finalize a subtree only after every child has finished, regardless of order.
            while frame is not None and frame.remaining_children == 0:
                if (
                    cutoff is not None
                    and frame.path != root
                    and frame.summary.status(cutoff) == "stale"
                ):
                    candidates.append(frame.path)
                parent = frame.parent
                if parent is not None:
                    parent.summary.include_child(frame.summary)
                    parent.remaining_children -= 1
                frame = parent
    stats.finish(options)
    stats.stats["ScanComplete"] = root_frame.summary.complete
    if cutoff is not None:
        stats.stats["RollupStatus"] = root_frame.summary.status(cutoff)
        stats.stats["ArchiveableDirs"] = sorted(candidates)
        stats.stats["ArchiveableDirsFixed"] = filter_children_paths(candidates)
    stats.stats["ExecutionTime"] = round(time.perf_counter() - started, 5)
    return stats.stats


def filter_children_paths(path_list: Sequence[str]) -> list[str]:
    """Keep only outermost candidates, comparing whole path components."""
    paths = {Path(os.path.abspath(path)) for path in path_list}
    retained: set[Path] = set()
    for path in sorted(paths, key=lambda item: (len(item.parts), str(item))):
        if not any(parent in retained for parent in path.parents):
            retained.add(path)
    return sorted(str(path) for path in retained)


def convert_size_human_friendly(size: int) -> list:
    if size < 1024:
        return [size, "Byte" if size == 1 else "Bytes"]
    value = float(size)
    for unit in SIZE_UNITS[1:]:
        value /= 1024
        if value < 1024 or unit == SIZE_UNITS[-1]:
            return [value, unit]
    raise ValueError("Invalid file size")


def size_bucket_label(bound: int) -> str:
    value, unit = convert_size_human_friendly(bound)
    return f"{value:g}{unit}"


def convert_seconds_human_friendly(seconds: float) -> str:
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        # Some filesystems allow timestamps outside datetime's supported range.
        return f"{seconds} (Unix timestamp)"


def format_results(
    stats: dict, *, human_friendly: bool = False, suppress_failures: bool = False
) -> dict:
    result = copy.deepcopy(stats)
    if human_friendly:
        for key in ("OldestFile", "NewestFile"):
            timestamp = result[key]["Age"]
            if timestamp is not None:
                result[key]["Age"] = convert_seconds_human_friendly(timestamp)
        result["HumanFriendlyTotalSize"] = convert_size_human_friendly(result["TotalSize"])
        result["LargestFiles"] = [
            (convert_size_human_friendly(size), path) for size, path in result["LargestFiles"]
        ]
    if suppress_failures:
        result["Failures"] = "Suppressed; see FailureCount"
    return result


def write_rollup(
    paths: Sequence[str],
    input_path: str | Path,
    destination: str | Path,
    use_time: str,
    *,
    human_readable: bool = False,
) -> Path:
    """Publish a complete UTF-8 export with a unique, portable filename."""
    destination = Path(destination)
    if not destination.is_dir():
        raise NotADirectoryError(f"Output directory does not exist: {destination}")
    source_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(input_path).name)[:64] or "root"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S-%f")
    label = "old_rollup_human_readable" if human_readable else "old_rollup"
    prefix = f"{source_name}_{label}_{use_time}time_{stamp}_"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            errors="backslashreplace",
            dir=destination,
            prefix=f".{prefix}",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            if human_readable:
                for path in paths:
                    # Escape line breaks so a filename cannot create extra rows.
                    output.write(
                        path.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n") + "\n"
                    )
            else:
                json.dump(list(paths), output, indent=2)
                output.write("\n")
        suffix = ".txt" if human_readable else ".json"
        final_path = destination / (temporary_path.name[1:-4] + suffix)
        os.replace(temporary_path, final_path)
        return final_path
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def existing_directory(value: str) -> Path:
    try:
        path = Path(os.path.abspath(Path(value).expanduser()))
        info = path.stat()
    except (OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    if not stat.S_ISDIR(info.st_mode):
        raise argparse.ArgumentTypeError(f"not an existing directory: {path}")
    return path


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report file sizes and find stale subdirectories.")
    parser.add_argument("path", type=existing_directory, help="Directory to scan")
    parser.add_argument(
        "-f", dest="human_friendly", action="store_true", help="Format sizes and timestamps (UTC)"
    )
    parser.add_argument(
        "--old-rollup",
        type=positive_integer,
        dest="days_old",
        metavar="DAYS",
        help="Find fully inspected subdirectories with all files at least DAYS old",
    )
    parser.add_argument(
        "--size-histogram", action="store_true", help="Count files by inclusive size upper bounds"
    )
    parser.add_argument(
        "--suppress-failures",
        action="store_true",
        help="Hide failure details while preserving their count and exit status",
    )
    parser.add_argument(
        "--top-files",
        type=positive_integer,
        nargs="?",
        const=10,
        dest="top_file_count",
        metavar="N",
        help="Return the N largest files (default: 10)",
    )
    parser.add_argument(
        "--save-rollup",
        type=existing_directory,
        dest="output_rollup_path",
        metavar="DIR",
        help="Save rollup JSON in an existing directory; requires --old-rollup",
    )
    parser.add_argument(
        "--save-rollup-human-readable",
        type=existing_directory,
        dest="output_rollup_path_human_readable",
        metavar="DIR",
        help="Save a readable rollup list; requires --old-rollup",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Skip matching basenames; repeatable and case-sensitive; blocks enclosing rollups",
    )
    parser.add_argument(
        "--profile-memory",
        action="store_true",
        help="Measure Python memory allocations during the scan",
    )
    parser.add_argument(
        "--workers",
        type=positive_integer,
        default=1,
        metavar="N",
        help="Scan up to N directories concurrently (default: 1)",
    )
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        "-a",
        dest="use_time",
        action="store_const",
        const="a",
        help="Use access time (depends on filesystem settings)",
    )
    time_group.add_argument(
        "-m",
        dest="use_time",
        action="store_const",
        const="m",
        help="Use modification time (default)",
    )
    time_group.add_argument(
        "-c",
        dest="use_time",
        action="store_const",
        const="c",
        help="Use ctime (metadata change on Unix; platform-dependent)",
    )
    parser.set_defaults(use_time="m")
    args = parser.parse_args(argv)
    if args.days_old is None and (
        args.output_rollup_path or args.output_rollup_path_human_readable
    ):
        parser.error("--save-rollup and --save-rollup-human-readable require --old-rollup DAYS")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    options = ScanOptions(
        days_old=args.days_old,
        use_time=args.use_time,
        top_file_count=args.top_file_count,
        size_histogram=args.size_histogram,
        exclusions=tuple(args.exclude),
        workers=args.workers,
    )
    owns_tracing = args.profile_memory and not tracemalloc.is_tracing()
    if owns_tracing:
        tracemalloc.start()
    try:
        stats = scan_filesystem(args.path, options)
        if args.profile_memory:
            current, peak = tracemalloc.get_traced_memory()
            stats["MemoryBytes"] = {"Current": current, "Peak": peak}
        print(f"Using {TIME_NAMES[args.use_time]} time")
        pprint.pprint(
            format_results(
                stats,
                human_friendly=args.human_friendly,
                suppress_failures=args.suppress_failures,
            ),
            sort_dicts=False,
        )
        for destination, human_readable in (
            (args.output_rollup_path, False),
            (args.output_rollup_path_human_readable, True),
        ):
            if destination is not None:
                saved = write_rollup(
                    stats["ArchiveableDirsFixed"],
                    args.path,
                    destination,
                    args.use_time,
                    human_readable=human_readable,
                )
                print(f"Saved rollup to {saved}")
        if stats["FailureCount"]:
            print(
                f"ERROR: Scan encountered {stats['FailureCount']} filesystem error(s); results are partial.",
                file=sys.stderr,
            )
            return 1
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Scan interrupted.", file=sys.stderr)
        return 130
    finally:
        if owns_tracing:
            tracemalloc.stop()


if __name__ == "__main__":
    sys.exit(main())
