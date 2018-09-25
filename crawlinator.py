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

def walk_dirs(data={}):
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
                try:
                    stat_info = os.stat(full_file_path)
                    file_dict_test = {full_file_path: stat_info}
                    tmp_file_list.append(file_dict_test)

                    # mtime = os.path.getmtime(full_file_path)
                    # atime = 
                    # # print(full_file_path + '   ---   ' + str(mtime) )#+ '   days')
                    # file_days_old = ((current_epoch - mtime) / 86400)
                    # if file_days_old < days_old:
                    #     data["old"] = False
                    #     break
                except Exception as e:
                    # print(e)
                    pass
            data["files"] = tmp_file_list

        if dirs:
            for d in dirs:
                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
                # tmp_dict["old"] = True
                tmp_dict["dirs"] = []

                walk_dirs(tmp_dict)

                # if not tmp_dict["old"]:
                #     data["old"] = False
                    
                list_of_dirs.append(tmp_dict)
                data["dirs"] = list_of_dirs

        break

# def print_path(data):
#     if dirs:
#         print(data["path"])

#     for d in data["dirs"]:
#         print_path(d)


def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path
    # days_old = args.days_old

    data = {}
    data["path"] = og_path

    walk_dirs(data)

    # print_path(data)

    # pp.pprint(data)

   
if __name__ == "__main__":
    main()
