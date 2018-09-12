#!/usr/bin/env python

import sys
import os
import argparse
import pprint

pp = pprint.PrettyPrinter(indent=4)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help='path')
    # parser.add_argument('days_old', action='store', type=int, help='how old do you want to check')

    return parser.parse_args()

epoch_one_day = 86400

def walk_dirs(data={}):
    for root, dirs, files in os.walk(data["path"]):
        list_of_dirs = []

        if files:
            tmp_file_list = files
            
            for t_file in tmp_file_list:
                full_file_path = root + '/' + t_file
                mtime = os.path.getmtime(full_file_path)
                mtime_days = mtime / 86400
                # print(full_file_path + '   ---   ' + str(mtime_days) + '   days')
                if mtime <  86400 * 30:
                    data["old"] = False
                    break
                data["old"] = True
                

        for d in dirs: 
            tmp_dict = {}
            tmp_dict["path"] = os.path.join(root, d)
            tmp_dict["old"] = False
            walk_dirs(tmp_dict)
            list_of_dirs.append(tmp_dict)

            data["dirs"] = list_of_dirs

        break

def main():
    args = parse_arguments() #Parse arguments

    og_path = args.path


    data = {}
    data["path"] = og_path

    walk_dirs(data)

    pp.pprint(data)




   

if __name__ == "__main__":
    main()
