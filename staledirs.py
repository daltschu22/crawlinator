#!/usr/bin/env python

import sys
import os
import argparse
import pprint
import time

pp = pprint.PrettyPrinter(indent=4)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help='path')
    parser.add_argument('days_old', action='store', type=int, help='how old do you want to check')

    return parser.parse_args()

epoch_one_day = 86400
current_epoch = time.time()

def walk_dirs(days_old, data={}):
    for root, dirs, files in os.walk(data["path"]):

        list_of_dirs = []
        data["old"] = True
        data["dirs"] = []

        if not files and not dirs:
            data["old"] = False
            return

        if files:
            tmp_file_list = files
            for t_file in tmp_file_list:
                full_file_path = os.path.join(root, t_file)
                try:
                    mtime = os.path.getmtime(full_file_path)
                    # print(full_file_path + '   ---   ' + str(mtime) )#+ '   days')
                    file_days_old = ((current_epoch - mtime) / 86400)
                    if file_days_old < days_old:
                        data["old"] = False
                        break
                except Exception as e:
                    # print(e)
                    pass

        if dirs:
            for d in dirs:
                tmp_dict = {}
                tmp_dict["path"] = os.path.join(root, d)
            
                walk_dirs(days_old, tmp_dict)

                if tmp_dict["old"] == False:
                    data["old"] = False
                    
                list_of_dirs.append(tmp_dict)
                data["dirs"] = list_of_dirs

        break

def print_path(data):
    if data["old"]:
        print(data["path"])

    for d in data["dirs"]:
        print_path(d)


def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path
    days_old = args.days_old

    data = {}
    data["path"] = og_path

    walk_dirs(days_old, data)

    print_path(data)

   
if __name__ == "__main__":
    main()
