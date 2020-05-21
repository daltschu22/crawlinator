#!/usr/bin/env python

import os
import argparse
import pprint
import time
import datetime
import checkpyversion
# import bisect
import json
import tracemalloc


pp = pprint.PrettyPrinter(indent=4)

epoch_one_day = 86400
current_epoch = time.time()
todays_date = datetime.datetime.today()

tracemalloc.start()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help="Filesystem path")
    parser.add_argument('-f', dest='human_friendly', action='store_true', help="Display sizes/times in a human friendly manner")
    # parser.add_argument('--old-rollup', action='store', type=int, dest='days_old', metavar='x days', help='Scan filesystem for directories with files older than # of days')
    # parser.add_argument('--size-histogram', action='store_true', help="Display sizes of files in a histogram")
    parser.add_argument('--suppress-failures', action='store_true', help="Supress failures from the output")
    # parser.add_argument('--top-files', action='store', type=int, nargs='?', const=10, dest='top_file_count', metavar='x largest files', help='Return the x largest files in the scan')
    # parser.add_argument('--save-rollup', action='store', type=str, dest='output_rollup_path', metavar='/path/to/save/json', help='Path to save rollup list into')
    # parser.add_argument('--save-rollup-human-readable', action='store', type=str, dest='output_rollup_path_human_readable', metavar='/path/to/save/list', help='Path to save rollup list into')

    # time_group = parser.add_mutually_exclusive_group()
    # time_group.add_argument('-m', dest='use_m_time', action='store_true', help="Use m_time instead of a_time")
    # time_group.add_argument('-c', dest='use_c_time', action='store_true', help="Use c_time instead of a_time")

    return parser.parse_args()


class FilesystemStats:
    """Class to hold filesystem stats"""

    def __init__(self):
        self.stats = {}

        # self.stats["TotalFiles"] = 0
        # self.stats["TotalSize"] = 0
        # self.stats["TotalDirs"] = 1
        # self.stats["OldestFile"] = {"Path": None, "Age": None}
        # self.stats["NewestFile"] = {"Path": None, "Age": None}
        self.stats["BadGIDs"] = 0
        self.stats["Failures"] = []
        # self.stats["LargestFiles"] = []
        self.stats["ExecutionTime"] = None


        self.bad_files = []




def walk_error(os_error, stats_object): 
    """#Garbage to get failures working because os.walk is janky"""
    # error = {os_error: os_error.filename}
    stats_object.stats["Failures"].append(os_error)


bad_gids = {
    63,
    40,
    50,
    54,
    65534,
    99,
    52,
    0,
    10,
    16,
    41,
    53,
    56,
    61,
    62,
    64,
    65,
    66,
    67,
    71,
    72,
    77,
    78,
    79,
    80,
    91,
    94,
    95,
    96,
    97,
    98,
    101,
    102,
    104,
    107,
    108,
    109,
    110,
    111,
    112,
    113,
    114,
    115,
    201,
    202,
    208,
    209,
    210,
    460,
    461,
    462,
    463,
    466,
    468,
    470,
    471,
    472,
    473,
    477,
    479,
    480,
    481,
    482,
    483,
    484,
    485,
    488,
    506,
    601,
    602,
    603,
    605,
    607,
    608,
    610,
    611,
    615,
    616,
    617,
    618,
    619,
    622,
    623,
    624,
    625,
    626,
    627,
    628,
    629,
    630,
    631,
    632,
    633,
    634,
    635,
    636,
    649,
    650,
    660,
    670,
    671,
    801,
    901,
    1001
}

def walk_dirs(stats_object, data={}, **kwargs):
    for root, dirs, files in os.walk(data["path"], onerror=lambda err: walk_error(err, stats_object)):
        # list_of_dirs = []
        # data["dirs"] = []


        if files:
        #     # tmp_file_list = []
            for file in files:
                full_file_path = os.path.join(root, file)

                try:
                    stat_info = os.stat(full_file_path)
                except Exception as e:
                    error_dict = {e: full_file_path}
                    stats_object.stats["Failures"].append(error_dict)
                    continue

                if stat_info.st_gid in bad_gids:
                    stats_object.stats["BadGIDs"] += 1
                    stats_object.bad_files.append(full_file_path)



        if dirs:
            for d in dirs:

                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
                tmp_dict["dirs"] = []


                walk_dirs(stats_object, tmp_dict, **kwargs)

        break




def check_read_perms(path):
    access = os.access(path, os.R_OK)

    return access


def main():
    args = parse_arguments()  # Parse arguments

    og_path = args.path
    human_friendly = args.human_friendly

    path_perms = check_read_perms(og_path)
    if not path_perms:
        print("ERROR: You dont have permission, or that path doesnt exist!")
        exit()


    use_time = 'a'

    data = {}
    data["path"] = og_path

    stats_object = FilesystemStats()


    optional_args = {}  # kwargs dictionary for any optional stuff


    walk_dirs(stats_object, data, **optional_args)  # Recursively walk the filesystem

    # Calculate time it took for script to run
    end_epoch_time = time.time()
    total_execution_time = round(end_epoch_time - current_epoch, 5)
    stats_object.stats["ExecutionTime"] = total_execution_time

    current, peak = tracemalloc.get_traced_memory()
    print(f"Current memory usage is {current / 10**6}MB; Peak was {peak / 10**6}MB")

    # Temporary print (Will make a dedicated results printing function later)
    if args.suppress_failures:
        stats_object.stats["Failures"] = "Suppressed!"
        pp.pprint(stats_object.stats)
    else:
        pp.pprint(stats_object.stats)


if __name__ == "__main__":
    main()
