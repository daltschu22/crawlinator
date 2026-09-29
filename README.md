# Crawlinator

Crawlinator reports file counts, sizes, timestamps, and stale subdirectories.
It reads filesystem metadata; it does not archive or delete files.

Requires **Python 3.11 or newer**. There are no runtime dependencies.

## Run or install

Run directly from this checkout:

```bash
python3 crawlinator.py /path/to/scan -f --top-files 10 --size-histogram
python3 crawlinator.py /path/to/scan --old-rollup 90
```

Or install the command in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
crawlinator /path/to/scan --old-rollup 90
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in
PowerShell. Use `python` in place of `python3` where appropriate.

## Options

| Option | Behavior |
| --- | --- |
| `-f` | Format timestamps in UTC, add a readable total size, and format largest-file sizes. |
| `--old-rollup DAYS` | Find subdirectories whose regular files are all at least this many days old. Requires a positive integer. |
| `--top-files [N]` | Return up to N largest files, largest first; N defaults to 10 and must be positive. Put the scan path first when omitting N. |
| `--size-histogram` | Count files in buckets with inclusive power-of-two size upper bounds. |
| `-m` | Use file modification time; this is the default. |
| `-a` | Use file access time, matching the original default. |
| `-c` | Use ctime: metadata-change time on Unix, with platform-dependent behavior elsewhere. |
| `--exclude GLOB` | Skip matching file or directory basenames. Repeatable, case-sensitive, and applied at every depth. Quote patterns to prevent shell expansion. |
| `--suppress-failures` | Hide error details; preserve `FailureCount` and the failing exit status. |
| `--save-rollup DIR` | Save the outermost candidate paths as a JSON array in an existing directory. Requires `--old-rollup`. |
| `--save-rollup-human-readable DIR` | Save the same candidates as a UTF-8 text list. Requires `--old-rollup`. |
| `--profile-memory` | Enable Python allocation tracing and include current/peak byte counts. |
| `--workers N` | Scan up to N directories concurrently. Requires a positive integer; default: 1. |

Get the complete CLI help with `python3 crawlinator.py --help`.

## Faster scans

For storage where metadata requests spend time waiting, try parallel directory
scanning:

```bash
python3 crawlinator.py /path/to/scan --old-rollup 90 --workers 4
```

Compare `ExecutionTime` with 1, 4, and 8 workers on the same tree. One worker is
the default and runs without a thread pool. Extra workers can help overlap
network or disk waits, but can slow down a scan of cached local files. A single
large directory is still processed by one worker; concurrency comes from
scanning different directories. Keep `--profile-memory` off when measuring speed,
and account for filesystem caching when comparing repeated runs.

At most N directory jobs are submitted at once. Each worker collects its own
statistics; the coordinator merges counts, size buckets, and largest-file lists.
Parent eligibility is decided only after all child subtrees finish. Results for
an unchanged tree are independent of worker completion order, including tied
timestamps and failure ordering. Ctrl+C cancels queued jobs and asks active
workers to stop between filesystem operations; an operation already blocked in
the filesystem must return before its worker can stop.

## What qualifies as stale?

A candidate must contain at least one successfully inspected regular file,
and every regular file in its subtree must have a selected timestamp at or
before the cutoff. The cutoff is captured once per scan; one day means 86,400
seconds. Directory timestamps are not used. Empty directories are not candidates,
but an empty child does not prevent an otherwise stale parent from qualifying.
The scan root itself is never included in the candidate list.

Hidden files, `Thumbs.db`, and `desktop.ini` are included by default. Exclusions,
symlinks (including broken links), Windows reparse points, and special files such
as sockets are skipped. A skipped entry or filesystem error makes its containing
subtree **unknown**, so that directory and its ancestors cannot qualify. Fully
inspected sibling subtrees can still qualify. The scan root must itself be a
directory, not a link.

For example, excluding a cache improves scan scope but prevents recommending a
whole parent directory whose cache was not inspected:

```bash
python3 crawlinator.py /path/to/scan --old-rollup 90 --exclude '.cache' --exclude '*.tmp'
```

Access time is not reliable evidence that a file is unused: mount options such as
`noatime` and `relatime` affect updates. Unix ctime tracks inode changes, not file
creation. See the [Linux timestamp documentation](https://man7.org/linux/man-pages/man7/inode.7.html).
These are reports from a live filesystem, not snapshots; files can change during
or after a scan. Recheck candidates before acting on a report.

## Results and exports

- `TotalFiles` counts successfully inspected regular file paths. `TotalSize` is
  their logical size in bytes, not allocated disk space. Hard links count once
  per path; symlink targets are not counted.
- `TotalDirs` counts directories whose listing was opened, including the root.
  `DiscoveredEntries` counts entries yielded by those listings; it includes
  skipped entries and entries whose metadata could not be read.
- `Failures` contains path, operation, error, and errno records. `FailureCount`
  remains available when error details are suppressed.
- `SkippedEntries` separates exclusions, symlinks/reparse points, and special
  files. `ScanComplete` is false if any entry was skipped or any operation failed.
- `OldestFile` and `NewestFile` use `Age` for the selected Unix timestamp, retained
  for compatibility with old reports. With `-f`, these become UTC strings; they
  remain `None` when no regular file was inspected.
- Histogram labels are inclusive upper bounds: `1KiB` covers 0–1,024 bytes,
  `2KiB` covers 1,025–2,048 bytes, and so on. Empty buckets are omitted.
- `ArchiveableDirs` contains all eligible subdirectories. `ArchiveableDirsFixed`
  removes descendants of already eligible parents and is the list exported.
  Paths are absolute and sorted. `RollupStatus` describes the root as `stale`,
  `active`, `empty`, or `unknown`.
- `ExecutionTime` is scan duration in seconds, measured with a monotonic clock.
  `MemoryBytes`, when requested, measures Python allocations rather than total
  process memory.

To export both formats:

```bash
mkdir -p /path/to/reports
python3 crawlinator.py /path/to/scan --old-rollup 90 \
  --save-rollup /path/to/reports \
  --save-rollup-human-readable /path/to/reports
```

Export filenames include the source directory's basename, selected time field,
UTC timestamp, and a random suffix. Files are written through a temporary file
and renamed after writing succeeds. The command prints each saved filename.
The JSON format preserves paths for machine use. The text format escapes
backslashes and line breaks; it is intended for reading, not shell execution.
Keep reports outside the scanned tree so previous exports do not affect later
scans. On a partial scan, exports contain only the subtrees that still qualified.

Exit statuses:

- `0`: No filesystem or export errors. Intentional skips can still make
  `ScanComplete` false and limit the candidate list.
- `1`: A scan or export failed, or the scan root is a link. Partial results may
  have been printed or exported.
- `2`: Invalid arguments, including missing directories or nonpositive counts.
- `130`: Interrupted with Ctrl+C.

## Changes from the original script

Modification time replaces access time as the default; use `-a` for access time.
Hidden files and Windows metadata files now count. Symlinks are skipped, errors
block enclosing rollups, invalid arguments fail explicitly, and top-file results
are ordered largest first. Memory profiling is optional. Output fields describing
failures, completeness, and skipped entries make partial scans visible.

The old unused Python-version helper has been removed. Installation declares the
supported Python version in `pyproject.toml`.

## Development checks

The GitHub Actions workflow checks formatting, lint, compilation, package
installation, and CLI startup on Python 3.11–3.14. No regression test suite is
included.

```bash
python -m pip install ruff
ruff check .
ruff format --check .
python -m compileall -q crawlinator.py
```
