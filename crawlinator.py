#!/usr/bin/env python

import sys
import os
import argparse
import pprint
import time
import datetime
import checkpyversion

pp = pprint.PrettyPrinter(indent=4)

epoch_one_day = 86400
current_epoch = time.time()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help="Filesystem path")
    parser.add_argument('-f', dest='human_friendly', action='store_true', help="Display sizes/times in a human friendly manner")
    parser.add_argument('--old-rollup', action='store', type=int, dest='days_old', metavar='x days', help='Scan filesystem for directories with files older than # of days')
    parser.add_argument('--size-histogram', action='store_true', help="Display sizes of files in a histogram")
    parser.add_argument('--suppress-failures', action='store_true', help="Supress failures from the output")

    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument('-m', dest='use_m_time', action='store_true', help="Use m_time instead of a_time")
    time_group.add_argument('-c', dest='use_c_time', action='store_true', help="Use c_time instead of a_time")

    return parser.parse_args()


class FilesystemStats:
    #Class to hold filesystem stats

    def __init__(self):
        self.stats = {}

        self.stats["TotalFiles"] = 0
        self.stats["TotalSize"] = 0
        self.stats["TotalDirs"] = 1
        self.stats["OldestFile"] = {"Path": None, "Age": None}
        self.stats["NewestFile"] = {"Path": None, "Age": None}
        self.stats["Failures"] = []
        self.stats["LargestFiles"] = []
        self.stats["ExecutionTime"] = None

    def update_oldestfile(self, file_time, full_file_path):
        #Check the current file against the running oldest file
        if self.stats["OldestFile"]["Age"] == None:
            self.stats["OldestFile"]["Age"] = file_time
            self.stats["OldestFile"]["Path"] = full_file_path

        if self.stats["OldestFile"]["Age"] > file_time:
            self.stats["OldestFile"]["Age"] = file_time
            self.stats["OldestFile"]["Path"] = full_file_path

    def update_newestfile(self, file_time, full_file_path):
        #Check the current file against the running newest file
        if self.stats["NewestFile"]["Age"] == None:
            self.stats["NewestFile"]["Age"] = file_time
            self.stats["NewestFile"]["Path"] = full_file_path

        if self.stats["NewestFile"]["Age"] < file_time:
            self.stats["NewestFile"]["Age"] = file_time
            self.stats["NewestFile"]["Path"] = full_file_path

    def update_sizehistogram(self, current_file_size):
        if "SizeHistogram" in self.stats:
            human_readable_size_list = convert_size_human_friendly(current_file_size)
            self.histogram_dict_parse(human_readable_size_list)

    def histogram_dict_parse(self, list_of_size):
    #Convert size to a multiple of 2, then add a counter to the entry in the dictionary that corresponds
    # size_in_human = list_of_size[0]
        size_human_int = round(list_of_size[0])
        size_suffix_str = str(list_of_size[1])

        if size_suffix_str == 'Byte' or size_suffix_str == 'Bytes':
            if "1KB" not in self.stats["SizeHistogram"]:
                self.stats["SizeHistogram"]["1KB"] = 1
            else:
                self.stats["SizeHistogram"]["1KB"] += 1
        else:
            size_rounded_pow = 1 << (size_human_int - 1).bit_length() #Black magic to find nearest power of 2
            size_rounded_with_suffix = str(size_rounded_pow) + size_suffix_str

            if size_rounded_with_suffix not in self.stats["SizeHistogram"]:
                self.stats["SizeHistogram"][size_rounded_with_suffix] = 1
            elif size_rounded_with_suffix in self.stats["SizeHistogram"]:
                self.stats["SizeHistogram"][size_rounded_with_suffix] += 1

    def check_largest_size(self, current_file_size):
        #Figure out the list of the top X files
        if len(stats["LargestFiles"]) < kwargs["LargestFilesNum"]:
            print("LESS THEN!", len(stats["LargestFiles"]))
            file_size_tuple = (full_file_path, current_file_size)
            if (len(stats["LargestFiles"]) == 0) or (current_file_size > stats["LargestFiles"][0][1]): 
                stats["LargestFiles"].insert(0, file_size_tuple)

def walk_error(os_error, stats_object): #Garbage to get failures working because os.walk is janky
    # error = {os_error: os_error.filename}
    stats_object.stats["Failures"].append(os_error)

def walk_dirs(stats_object, data={}, **kwargs):
    for root, dirs, files in os.walk(data["path"], onerror=lambda err: walk_error(err, stats_object)):
        
        list_of_dirs = []
        data["dirs"] = []

        if "days_old" in kwargs:
            data["old"] = True

        if not files and not dirs:
            data["old"] = False
            return

        if files:
            # tmp_file_list = []
            for file in files:
                full_file_path = os.path.join(root, file)
                stats_object.stats["TotalFiles"] += 1
                try:
                    stat_info = os.stat(full_file_path)
                except Exception as e:
                    error_dict = {e: full_file_path}
                    stats_object.stats["Failures"].append(error_dict)
                    continue

                file_stats = {full_file_path: full_file_path, "StatInfo": stat_info} #Get stats of the file

                #Determine which time value to use for oldest/newest files
                use_time = kwargs.get('use_time')
                if use_time == 'c':
                    file_time = file_stats["StatInfo"].st_ctime
                if use_time == 'm':
                    file_time = file_stats["StatInfo"].st_mtime
                if use_time == 'a':
                    file_time = file_stats["StatInfo"].st_atime

                stats_object.update_oldestfile(file_time, full_file_path)
                stats_object.update_newestfile(file_time, full_file_path)

                current_file_size = file_stats["StatInfo"].st_size #Get current file size
                stats_object.stats["TotalSize"] += current_file_size #Add to the running size total

                stats_object.update_sizehistogram(current_file_size)

                if "days_old" in kwargs:
                    file_days_old = ((current_epoch - file_time) / 86400)
                    if file_days_old < kwargs.get("days_old"):
                        data["old"] = False

                # tmp_file_list.append(file_stats) #Are these needed?
            # data["files"] = tmp_file_list #Are these needed?

        if dirs:
            for d in dirs:
                stats_object.stats["TotalDirs"] += 1

                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
                tmp_dict["dirs"] = []

                if "days_old" in kwargs:
                    tmp_dict["old"] = True

                walk_dirs(stats_object, tmp_dict, **kwargs)

                if "old" in tmp_dict and not tmp_dict["old"]:
                    data["old"] = False
                    
                list_of_dirs.append(tmp_dict)
                data["dirs"] = list_of_dirs

                if "old" in data and data["old"]:
                    stats_object.stats["ArchiveableDirs"].append(tmp_dict["path"])

        break

# def print_path(data):
#     if data["old"]:
#         print(data["path"])

#     for d in data["dirs"]:
#         print_path(d)


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

def check_read_perms(path):
    access = os.access(path, os.R_OK)

    return access

def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path
    human_friendly = args.human_friendly

    path_perms = check_read_perms(og_path)
    if not path_perms:
        print("You dont have permission, or that path doesnt exist!")
        exit()

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

    stats_object = FilesystemStats()

    if args.days_old:
        stats_object.stats["ArchiveableDirs"] = []

    optional_args = {} #kwargs dictionary for any optional stuff
    if args.days_old:
        optional_args["days_old"] = args.days_old
    if args.size_histogram:
        size_histogram = {}
        stats_object.stats["SizeHistogram"] = size_histogram
    optional_args["use_time"] = use_time

    optional_args["LargestFilesNum"] = 10

    walk_dirs(stats_object, data, **optional_args) #Recursively walk the filesystem

    if stats_object.stats["TotalFiles"] > 0 and human_friendly:
        stats_object.stats["OldestFile"]["Age"] = convert_seconds_human_friendly(stats_object.stats["OldestFile"]["Age"])
        stats_object.stats["NewestFile"]["Age"] = convert_seconds_human_friendly(stats_object.stats["NewestFile"]["Age"])
    if stats_object.stats["TotalSize"] and human_friendly:
        stats_object.stats["HumanFriendlyTotalSize"] = convert_size_human_friendly(stats_object.stats["TotalSize"])

    #Calculate time it took for script to run
    end_epoch_time = time.time()
    total_execution_time = round(end_epoch_time - current_epoch, 5)
    stats_object.stats["ExecutionTime"] = total_execution_time

    #Temporary print (Will make a dedicated results printing function later)
    if args.suppress_failures:
        stats_object.stats["Failures"] = "Suppressed!"
        pp.pprint(stats_object.stats)
    else:
        pp.pprint(stats_object.stats)


    # print_path(data)
    # pp.pprint(data)

   
if __name__ == "__main__":
    main()
