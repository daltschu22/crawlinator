#!/usr/bin/env python

import sys
import os
import argparse
import pprint
import time

pp = pprint.PrettyPrinter(indent=4)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help='Filesystem path')
    # parser.add_argument('days_old', action='store', type=int, help='How many days old do the files have to be')

    return parser.parse_args()

epoch_one_day = 86400
current_epoch = time.time()


def walk_dirs(stats, data={}):
    for root, dirs, files in os.walk(data["path"]):

        list_of_dirs = []
        # data["old"] = True
        data["dirs"] = []

        if not files and not dirs:
            # data["old"] = False
            return

        if files:
            tmp_file_list = []
            for file in files:
                full_file_path = os.path.join(root, file)
                stats["TotalFiles"] += 1
                try:
                    stat_info = os.stat(full_file_path)
                except Exception as e:
                    # print(e)
                    pass

                file_stats = {full_file_path: full_file_path, "stat_info": stat_info}
                stats["TotalSize"] += file_stats["stat_info"].st_size
                tmp_file_list.append(file_stats)

            data["files"] = tmp_file_list

        if dirs:
            for d in dirs:
                stats["TotalDirs"] += 1

                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
                # tmp_dict["old"] = True
                tmp_dict["dirs"] = []

                walk_dirs(stats, tmp_dict)

                # if not tmp_dict["old"]:
                #     data["old"] = False
                    
                list_of_dirs.append(tmp_dict)
                data["dirs"] = list_of_dirs

        break

def print_path(data):
    pp.pprint(data)

    for d in data["dirs"]:
        print_path(d)


def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path
    # days_old = args.days_old

    stats = {}
    stats["TotalFiles"] = 0
    stats["TotalSize"] = 0
    stats["TotalDirs"] = 1

    data = {}
    data["path"] = og_path

    walk_dirs(stats, data)

    # print_path(data)

    print(stats)
    # pp.pprint(data)

   
if __name__ == "__main__":
    main()
