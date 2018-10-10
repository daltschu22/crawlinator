#!/usr/bin/env python

import sys
import os
import argparse
import pprint
import time
import datetime

pp = pprint.PrettyPrinter(indent=4)

epoch_one_day = 86400
current_epoch = time.time()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help="Filesystem path")
    parser.add_argument('-f', dest='human_friendly', action='store_true', help="Display sizes/times in a human friendly manner")
    parser.add_argument('--old-rollup', action='store', type=int, dest='days_old', metavar='x days', help='Scan filesystem for directories with files older than # of days')
    parser.add_argument('--size-histogram', action='store_true', help="Display sizes of files in a histogram")

    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument('-m', dest='use_m_time', action='store_true', help="Use m_time instead of a_time")
    time_group.add_argument('-c', dest='use_c_time', action='store_true', help="Use c_time instead of a_time")

    return parser.parse_args()

def walk_dirs(stats, data={}, **kwargs):
    for root, dirs, files in os.walk(data["path"]):

        list_of_dirs = []
        data["dirs"] = []

        if 'days_old' in kwargs:
            data["old"] = True

        use_time = kwargs.get('use_time')

        if not files and not dirs:
            data["old"] = False
            return

        if files:
            # tmp_file_list = []
            for file in files:
                full_file_path = os.path.join(root, file)
                stats["TotalFiles"] += 1
                try:
                    stat_info = os.stat(full_file_path)
                except Exception as e:
                    print(e)
                    continue

                file_stats = {full_file_path: full_file_path, "StatInfo": stat_info} #Get stats of the file

                #Determine which time value to use for oldest/newest files
                if use_time == 'c':
                    file_time = file_stats["StatInfo"].st_ctime
                if use_time == 'm':
                    file_time = file_stats["StatInfo"].st_mtime
                if use_time == 'a':
                    file_time = file_stats["StatInfo"].st_atime

                if stats["OldestFileAge"] == None:
                    stats["OldestFileAge"] = file_time
                    stats["OldestFileName"] = full_file_path

                if stats["NewestFileAge"] == None:
                    stats["NewestFileAge"] = file_time
                    stats["NewestFileName"] = full_file_path

                if stats["OldestFileAge"] > file_time:
                    stats["OldestFileAge"] = file_time
                    stats["OldestFileName"] = full_file_path

                if stats["NewestFileAge"] < file_time:
                    stats["NewestFileAge"] = file_time
                    stats["NewestFileName"] = full_file_path

                stats["TotalSize"] += file_stats["StatInfo"].st_size #Add to the running size total

                if "SizeHistogram" in stats:
                    human_readable_size_list = convert_size_human_friendly(file_stats["StatInfo"].st_size)
                    histogram_dict_parse(human_readable_size_list, stats)

                if 'days_old' in kwargs:
                    file_days_old = ((current_epoch - file_time) / 86400)
                    if file_days_old < kwargs.get('days_old'):
                        data["old"] = False

                # tmp_file_list.append(file_stats) #Are these needed?
            # data["files"] = tmp_file_list #Are these needed?

        if dirs:
            for d in dirs:
                stats["TotalDirs"] += 1

                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
                tmp_dict["dirs"] = []

                if 'days_old' in kwargs:
                    tmp_dict["old"] = True

                walk_dirs(stats, tmp_dict, **kwargs)

                if "old" in tmp_dict and not tmp_dict["old"]:
                    data["old"] = False
                    
                list_of_dirs.append(tmp_dict)
                data["dirs"] = list_of_dirs

                if "old" in data and data["old"] == True:
                    stats["ArchiveableDirs"].append(tmp_dict["path"])

        break

# def print_path(data):
#     if data["old"]:
#         print(data["path"])

#     for d in data["dirs"]:
#         print_path(d)

def histogram_dict_parse(list_of_size, stats):
    #Convert size to a multiple of 2, then add a counter to the entry in the dictionary that corresponds
    # size_in_human = list_of_size[0]
    size_human_int = round(list_of_size[0])
    size_suffix_str = str(list_of_size[1])

    if size_suffix_str == 'Byte' or size_suffix_str == 'Bytes':
        if "1KB" not in stats["SizeHistogram"]:
            stats["SizeHistogram"]["1KB"] = 1
        else:
            stats["SizeHistogram"]["1KB"] += 1
    else:
        size_rounded_pow = 1 << (size_human_int - 1).bit_length() #Black magic to find nearest power of 2
        size_rounded_with_suffix = str(size_rounded_pow) + size_suffix_str

        if size_rounded_with_suffix not in stats["SizeHistogram"]:
            stats["SizeHistogram"][size_rounded_with_suffix] = 1
        elif size_rounded_with_suffix in stats["SizeHistogram"]:
            stats["SizeHistogram"][size_rounded_with_suffix] += 1

def convert_size_human_friendly(size):
    #Return the given bytes as a human friendly KB, MB, GB, or TB string
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
    #Return a seconds value as a datetime formatted string
    mod_timestamp = datetime.datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M:%S")

    return mod_timestamp

def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path
    human_friendly = args.human_friendly
    # days_old = args.days_old

    if args.use_c_time:
        print("Using C_TIME")
        use_time = 'c'
    elif args.use_m_time:
        print("Using M_TIME")
        use_time = 'm'
    else:
        print("Using default A_TIME")
        use_time = 'a'

    data = {}
    data["path"] = og_path

    stats = {}
    stats["TotalFiles"] = 0
    stats["TotalSize"] = 0
    stats["TotalDirs"] = 1
    stats["OldestFileAge"] = None
    stats["NewestFileAge"] = None
    stats["OldestFileName"] = None
    stats["NewestFileName"] = None

    if args.days_old:
        ArchiveableDirs = []
        stats["ArchiveableDirs"] = ArchiveableDirs

    kwargs_dict = {} #kwargs dictionary for any optional stuff
    if args.days_old:
        kwargs_dict.update({'days_old' : args.days_old})
    if args.size_histogram:
        size_histogram = {}
        stats["SizeHistogram"] = size_histogram
    kwargs_dict.update({'use_time' : use_time})


    walk_dirs(stats, data, **kwargs_dict) #Recursively walk the filesystem

    if stats["TotalFiles"] > 0 and human_friendly:
        stats["OldestFileAge"] = convert_seconds_human_friendly(stats["OldestFileAge"])
        stats["NewestFileAge"] = convert_seconds_human_friendly(stats["NewestFileAge"])
    if stats["TotalSize"] and human_friendly:
        stats["HumanFriendlyTotalSize"] = convert_size_human_friendly(stats["TotalSize"])
        stats["TotalSize"] = convert_size_human_friendly(stats["TotalSize"])


    # print_path(data)


    pp.pprint(stats)
    # pp.pprint(data)

   
if __name__ == "__main__":
    main()
