#!/usr/bin/env python

import os
import argparse
import pprint
import time
import datetime
import checkpyversion
import bisect
import json
import tracemalloc
import multiprocessing as mp
from functools import partial
from collections import defaultdict

pp = pprint.PrettyPrinter(indent=4)

epoch_one_day = 86400
current_epoch = time.time()
todays_date = datetime.datetime.today()

tracemalloc.start()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help="Filesystem path")
    parser.add_argument('-f', dest='human_friendly', action='store_true', help="Display sizes/times in a human friendly manner")
    parser.add_argument('--old-rollup', action='store', type=int, dest='days_old', metavar='x days', help='Scan filesystem for directories with files older than # of days')
    parser.add_argument('--size-histogram', action='store_true', help="Display sizes of files in a histogram")
    parser.add_argument('--time-histogram', action='store_true', help="Display file ages in a histogram with size totals")
    parser.add_argument('--suppress-failures', action='store_true', help="Supress failures from the output")
    parser.add_argument('--top-files', action='store', type=int, nargs='?', const=10, dest='top_file_count', metavar='x largest files', help='Return the x largest files in the scan')
    parser.add_argument('--save-rollup', action='store', type=str, dest='output_rollup_path', metavar='/path/to/save/json', help='Path to save rollup list into')
    parser.add_argument('--save-rollup-human-readable', action='store', type=str, dest='output_rollup_path_human_readable', metavar='/path/to/save/list', help='Path to save rollup list into')
    parser.add_argument('--jobs', '-j', type=int, default=mp.cpu_count(), help='Number of parallel jobs (default: number of CPU cores)')

    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument('-m', dest='use_m_time', action='store_true', help="Use m_time instead of a_time")
    time_group.add_argument('-c', dest='use_c_time', action='store_true', help="Use c_time instead of a_time")

    return parser.parse_args()


class FilesystemStats:
    def __init__(self):
        self.stats = defaultdict(int)
        self.stats.update({
            "TotalFiles": 0,
            "TotalSize": 0,
            "TotalDirs": 1,
            "OldestFile": {"Path": None, "Age": None},
            "NewestFile": {"Path": None, "Age": None},
            "Failures": [],
            "LargestFiles": [],
            "ExecutionTime": None,
            "SizeHistogram": {},
            "TimeHistogram": {}
        })
        self.time_window_size = 30

    def merge_stats(self, other_stats):
        """Merge another FilesystemStats object into this one"""
        self.stats["TotalFiles"] += other_stats["TotalFiles"]
        self.stats["TotalSize"] += other_stats["TotalSize"]
        self.stats["TotalDirs"] += other_stats["TotalDirs"]
        self.stats["Failures"].extend(other_stats["Failures"])
        
        # Merge histograms if they exist
        if "SizeHistogram" in other_stats:
            for size, count in other_stats["SizeHistogram"].items():
                self.stats["SizeHistogram"][size] = self.stats["SizeHistogram"].get(size, 0) + count
        
        if "TimeHistogram" in other_stats:
            for window, data in other_stats["TimeHistogram"].items():
                if window not in self.stats["TimeHistogram"]:
                    self.stats["TimeHistogram"][window] = data.copy()
                else:
                    self.stats["TimeHistogram"][window]["count"] += data["count"]
                    self.stats["TimeHistogram"][window]["total_size"] += data["total_size"]

        # Update oldest/newest files
        if other_stats["OldestFile"]["Age"] is not None:
            if (self.stats["OldestFile"]["Age"] is None or 
                other_stats["OldestFile"]["Age"] < self.stats["OldestFile"]["Age"]):
                self.stats["OldestFile"] = other_stats["OldestFile"]

        if other_stats["NewestFile"]["Age"] is not None:
            if (self.stats["NewestFile"]["Age"] is None or 
                other_stats["NewestFile"]["Age"] > self.stats["NewestFile"]["Age"]):
                self.stats["NewestFile"] = other_stats["NewestFile"]

        # Merge and sort largest files
        if "LargestFiles" in other_stats and other_stats["LargestFiles"]:
            self.stats["LargestFiles"].extend(other_stats["LargestFiles"])
            self.stats["LargestFiles"].sort(reverse=True)
            if len(self.stats["LargestFiles"]) > 10:  # Assuming we want top 10
                self.stats["LargestFiles"] = self.stats["LargestFiles"][:10]


def process_directory(directory, use_time, options):
    """Process a single directory and return its stats"""
    stats = defaultdict(int)
    stats.update({
        "TotalFiles": 0,
        "TotalSize": 0,
        "TotalDirs": 1,
        "OldestFile": {"Path": None, "Age": None},
        "NewestFile": {"Path": None, "Age": None},
        "Failures": [],
        "LargestFiles": []
    })
    
    if options.get("size_histogram"):
        stats["SizeHistogram"] = {}
    if options.get("time_histogram"):
        stats["TimeHistogram"] = {}

    try:
        # Use scandir instead of walk for better performance
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    # Use lstat instead of stat to avoid following symlinks
                    stat_info = entry.stat(follow_symlinks=False)
                    
                    if entry.is_dir(follow_symlinks=False):
                        stats["TotalDirs"] += 1
                        # Recursively process subdirectory
                        sub_stats = process_directory(entry.path, use_time, options)
                        for key, value in sub_stats.items():
                            if isinstance(value, (int, float)):
                                stats[key] += value
                            elif isinstance(value, list):
                                if not isinstance(stats[key], list):
                                    stats[key] = []
                                stats[key].extend(value)
                            elif isinstance(value, dict):
                                if key == "TimeHistogram":
                                    if key not in stats:
                                        stats[key] = {}
                                    for window, data in value.items():
                                        if window not in stats[key]:
                                            stats[key][window] = data.copy()
                                        else:
                                            stats[key][window]["count"] += data["count"]
                                            stats[key][window]["total_size"] += data["total_size"]
                                elif key == "SizeHistogram":
                                    if key not in stats:
                                        stats[key] = {}
                                    for size, count in value.items():
                                        stats[key][size] = stats[key].get(size, 0) + count
                                else:
                                    if key not in stats:
                                        stats[key] = value.copy()
                                    else:
                                        stats[key].update(value)

                            # Update oldest/newest files
                            if key == "OldestFile" and value["Age"] is not None:
                                if stats[key]["Age"] is None or value["Age"] < stats[key]["Age"]:
                                    stats[key] = value.copy()
                            elif key == "NewestFile" and value["Age"] is not None:
                                if stats[key]["Age"] is None or value["Age"] > stats[key]["Age"]:
                                    stats[key] = value.copy()
                    
                    elif entry.is_file(follow_symlinks=False):
                        # Skip certain files
                        if entry.name.lower() in ('thumbs.db', 'desktop.ini') or entry.name.startswith('.'):
                            continue

                        stats["TotalFiles"] += 1
                        file_size = stat_info.st_size
                        stats["TotalSize"] += file_size

                        # Get appropriate time value
                        if use_time == 'c':
                            file_time = stat_info.st_ctime
                        elif use_time == 'm':
                            file_time = stat_info.st_mtime
                        else:
                            file_time = stat_info.st_atime

                        # Update oldest/newest
                        if stats["OldestFile"]["Age"] is None or file_time < stats["OldestFile"]["Age"]:
                            stats["OldestFile"] = {"Path": entry.path, "Age": file_time}
                        if stats["NewestFile"]["Age"] is None or file_time > stats["NewestFile"]["Age"]:
                            stats["NewestFile"] = {"Path": entry.path, "Age": file_time}

                        # Update histograms
                        if options.get("size_histogram"):
                            size_list = convert_size_human_friendly(file_size)
                            update_size_histogram(stats, size_list)
                        
                        if options.get("time_histogram"):
                            update_time_histogram(stats, file_time, file_size)

                        # Track largest files
                        if options.get("top_file_count"):
                            update_largest_files(stats, file_size, entry.path, options["top_file_count"])

                except (PermissionError, OSError) as e:
                    stats["Failures"].append({str(e): entry.path})

    except (PermissionError, OSError) as e:
        stats["Failures"].append({str(e): directory})

    return stats


def update_size_histogram(stats, size_list):
    size_human_int = round(size_list[0])
    size_suffix_str = str(size_list[1])

    if size_suffix_str == 'Byte' or size_suffix_str == 'Bytes':
        key = "1KB"
    else:
        size_rounded_pow = 1 << (size_human_int - 1).bit_length()
        key = f"{size_rounded_pow}{size_suffix_str}"

    stats["SizeHistogram"][key] = stats["SizeHistogram"].get(key, 0) + 1


def update_time_histogram(stats, file_time, file_size):
    file_age_days = (current_epoch - file_time) / epoch_one_day
    
    if file_age_days <= 1:
        window_name = "Today"
    else:
        window_number = 1 << (int(file_age_days / 30) - 1).bit_length()
        if window_number == 0:
            window_number = 1
        window_name = f"{window_number * 30} days"

    if window_name not in stats["TimeHistogram"]:
        stats["TimeHistogram"][window_name] = {"count": 0, "total_size": 0}
    
    stats["TimeHistogram"][window_name]["count"] += 1
    stats["TimeHistogram"][window_name]["total_size"] += file_size


def update_largest_files(stats, file_size, file_path, limit):
    file_tuple = (file_size, file_path)
    if not stats["LargestFiles"]:
        stats["LargestFiles"].append(file_tuple)
    else:
        bisect_num = bisect.bisect(stats["LargestFiles"], file_tuple)
        stats["LargestFiles"].insert(bisect_num, file_tuple)
        if len(stats["LargestFiles"]) > limit:
            stats["LargestFiles"].pop(0)


def process_chunk(chunk, use_time, options):
    """Process a chunk of directories in parallel"""
    stats = defaultdict(int)
    stats.update({
        "TotalFiles": 0,
        "TotalSize": 0,
        "TotalDirs": 1,
        "OldestFile": {"Path": None, "Age": None},
        "NewestFile": {"Path": None, "Age": None},
        "Failures": [],
        "LargestFiles": []
    })
    
    if options.get("size_histogram"):
        stats["SizeHistogram"] = {}
    if options.get("time_histogram"):
        stats["TimeHistogram"] = {}

    for directory in chunk:
        dir_stats = process_directory(directory, use_time, options)
        for key, value in dir_stats.items():
            if isinstance(value, (int, float)):
                stats[key] += value
            elif isinstance(value, list):
                if not isinstance(stats[key], list):
                    stats[key] = []
                stats[key].extend(value)
            elif isinstance(value, dict):
                if key == "TimeHistogram":
                    if key not in stats:
                        stats[key] = {}
                    for window, data in value.items():
                        if window not in stats[key]:
                            stats[key][window] = data.copy()
                        else:
                            stats[key][window]["count"] += data["count"]
                            stats[key][window]["total_size"] += data["total_size"]
                elif key == "SizeHistogram":
                    if key not in stats:
                        stats[key] = {}
                    for size, count in value.items():
                        stats[key][size] = stats[key].get(size, 0) + count
                else:
                    if key not in stats:
                        stats[key] = value.copy()
                    else:
                        stats[key].update(value)

            # Update oldest/newest files
            if key == "OldestFile" and value["Age"] is not None:
                if stats[key]["Age"] is None or value["Age"] < stats[key]["Age"]:
                    stats[key] = value.copy()
            elif key == "NewestFile" and value["Age"] is not None:
                if stats[key]["Age"] is None or value["Age"] > stats[key]["Age"]:
                    stats[key] = value.copy()

    return stats


def convert_size_human_friendly(size):
    # Return the given bytes as a human friendly KB, MB, GB, or TB string
    B = float(size)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    size_list = []

    if B < KB:
        size_list.insert(0, B)
        size_list.insert(1, '{0}'.format('Bytes' if 0 == B > 1 else 'Byte'))
    elif KB <= B < MB:
        size_list.insert(0, B/KB)
        size_list.insert(1, 'KiB')
    elif MB <= B < GB:
        size_list.insert(0, B/MB)
        size_list.insert(1, 'MiB')
    elif GB <= B < TB:
        size_list.insert(0, B/GB)
        size_list.insert(1, 'GiB')
    elif TB <= B:
        size_list.insert(0, B/TB)
        size_list.insert(1, 'TiB')

    return size_list


def convert_seconds_human_friendly(seconds):
    # Return a seconds value as a datetime formatted string
    mod_timestamp = datetime.datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M:%S")

    return mod_timestamp


def check_read_perms(path):
    access = os.access(path, os.R_OK)

    return access


def filter_children_paths(path_list):
    """ Iterate through list of paths and remove any extraneous ones."""
    # Sort list
    sorted_path_list = sorted(path_list)

    i = 0
    while i < len(sorted_path_list):
        if i == (len(sorted_path_list) - 1):
            break
        if '{}/'.format(sorted_path_list[i]) in '{}/'.format(sorted_path_list[i+1]):
            print("DELETING {}".format(sorted_path_list[i+1]))
            del sorted_path_list[i+1]
        else:
            i += 1

    return sorted_path_list


def write_object_to_json_file(object_to_json, input_path, path_to_save, use_time):
    """Save the list of directories that match the old_rollup criteria to a json object in a defined path."""
    todays_date_formatted = todays_date.strftime("%Y-%m-%d-%H-%M-%S")

    if os.path.exists(path_to_save):
        dir_path = os.path.join(path_to_save, '')
        input_path_under = input_path.replace('/', '_')
        filename_to_save = '{}_old_rollup_{}time_{}.json'.format(input_path_under, use_time, todays_date_formatted)
        path_with_file = '{}{}'.format(dir_path, filename_to_save)
        with open(path_with_file, 'w') as outfile:
            json.dump(object_to_json, outfile)

def write_files_human_readable(json_object, input_path, path_to_save, use_time):
    """Save the list of directories that match the old_rollup criteria to a human readable file."""
    todays_date_formatted = todays_date.strftime("%Y-%m-%d-%H-%M-%S")

    if os.path.exists(path_to_save):
        dir_path = os.path.join(path_to_save, '')
        input_path_under = input_path.replace('/', '_')
        filename_to_save = '{}_old_rollup_human_readable_{}time_{}.txt'.format(input_path_under, use_time, todays_date_formatted)
        path_with_file = '{}{}'.format(dir_path, filename_to_save)
        with open(path_with_file, 'w') as outfile:
            for path in json_object:
                outfile.write('{}\n'.format(path))

def main():
    args = parse_arguments()
    
    start_time = time.time()  # Start timing
    
    if not check_read_perms(args.path):
        print("ERROR: You dont have permission, or that path doesnt exist!")
        exit(1)

    use_time = 'c' if args.use_c_time else 'm' if args.use_m_time else 'a'
    print(f"Using {use_time.upper()}_TIME")

    # Prepare options for processing
    options = {
        "size_histogram": args.size_histogram,
        "time_histogram": args.time_histogram,
        "top_file_count": args.top_file_count,
        "days_old": args.days_old
    }

    # Get list of all directories for parallel processing
    directories = []
    try:
        with os.scandir(args.path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    directories.append(entry.path)
    except (PermissionError, OSError) as e:
        print(f"Error accessing path: {e}")
        exit(1)

    # If no subdirectories, just process the main directory
    if not directories:
        directories = [args.path]

    # Split directories into chunks for parallel processing
    chunk_size = max(1, len(directories) // args.jobs)
    chunks = [directories[i:i + chunk_size] for i in range(0, len(directories), chunk_size)]

    # Process chunks in parallel
    with mp.Pool(args.jobs) as pool:
        results = pool.map(partial(process_chunk, use_time=use_time, options=options), chunks)

    # Merge results
    stats_object = FilesystemStats()
    for result in results:
        stats_object.merge_stats(result)

    # Calculate execution time
    stats_object.stats["ExecutionTime"] = round(time.time() - start_time, 5)

    # Post-process results
    if args.human_friendly:
        if stats_object.stats["TotalFiles"] > 0:
            stats_object.stats["OldestFile"]["Age"] = convert_seconds_human_friendly(stats_object.stats["OldestFile"]["Age"])
            stats_object.stats["NewestFile"]["Age"] = convert_seconds_human_friendly(stats_object.stats["NewestFile"]["Age"])
        if stats_object.stats["TotalSize"]:
            stats_object.stats["HumanFriendlyTotalSize"] = convert_size_human_friendly(stats_object.stats["TotalSize"])
            if "TimeHistogram" in stats_object.stats:
                for window in stats_object.stats["TimeHistogram"]:
                    size = stats_object.stats["TimeHistogram"][window]["total_size"]
                    stats_object.stats["TimeHistogram"][window]["total_size_human"] = convert_size_human_friendly(size)

    # Save results if requested
    if args.output_rollup_path:
        write_object_to_json_file(stats_object.stats.get("ArchiveableDirsFixed", []), 
                                args.path, args.output_rollup_path, use_time)
    if args.output_rollup_path_human_readable:
        write_files_human_readable(stats_object.stats.get("ArchiveableDirsFixed", []), 
                                 args.path, args.output_rollup_path_human_readable, use_time)

    # Print results
    if args.suppress_failures:
        stats_object.stats["Failures"] = "Suppressed!"
    pp.pprint(dict(stats_object.stats))

    # Memory stats
    current, peak = tracemalloc.get_traced_memory()
    print(f"Current memory usage is {current / 10**6}MB; Peak was {peak / 10**6}MB")


if __name__ == "__main__":
    main()
