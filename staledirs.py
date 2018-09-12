#!/usr/bin/env python

import sys
import os
import argparse
import pprint
from functools import reduce

pp = pprint.PrettyPrinter(indent=4)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find stale dirs")
    parser.add_argument('path', metavar='/filesysem/path', help='path')
    # parser.add_argument('days_old', help='how old do you want to check')

    return parser.parse_args()


# # def get_directory_structure(rootdir):
# #     dir = {}
# #     rootdir = rootdir.rstrip(os.sep)
# #     start = rootdir.rfind(os.sep) + 1

# #     for path, dirs, files in os.walk(rootdir):
# #         folders = path[start:].split(os.sep)
# #         subdir = dict.fromkeys(files)
# #         parent = reduce(dict.get, folders[:-1], dir)
# #         parent[folders[-1]] = subdir
# #     return dir


# class FileSystem:
#     def __init__(self, clean_path):
#         # self.og_path = arg_path
#         # self.dirs = []
#         # self.name = clean_path
#         # self.child = 
#         self.full = {}
#         # dir_list = []
#         # self.full.update({'dirs': dir_list})
#         # for root, dirs, files in os.walk(clean_path, followlinks=False):
#         #     # self.full.update({'dirs': dirs})
#         #     self.full.update({'root': root, 'files': files})
#         #     for dir in dirs:
#         #         fullpath = str(self.full['root'] + '/' + dir)
#         #         entry = {'name': dir, 'fullpath': fullpath}
#         #         self.full['dirs'].append(entry)
#             # break

#     # def walk_dir(self, dir_entry):
#     #     dir_list = []
#     #     dir_entry.update({'dirs': dir_list})
#     #     for root, dirs, files in os.walk(dir_entry, followlinks=False):
#     #         # self.full.update({'dirs': dirs})
#     #         dir_entry.update({'root': root, 'files': files})
#     #         for dir in dirs:
#     #             entry = {'root': dir}
#     #             dir_entry['dirs'].append(entry)
#     #         break

#     #     return dir_entry

    
# def set_leaf(tree, branches, leaf):

#     # print('\n\n\n')
#     # # print("Tree")
#     # # pp.pprint(tree)
#     # print("Branches")
#     # pp.pprint(branches)
#     # print("leaf")
#     # pp.pprint(leaf)
    

#     if len(branches) == 1:
#         tree[branches[0]] = leaf
#         # print("Len of branches equals 1")
#         # print(tree[branches[0]])
#         return
#     if not branches[0] in tree:
#         tree[branches[0]] = {}
#     set_leaf(tree[branches[0]], branches[1:], leaf)

# def set_tree(path):
#     startpath = path
#     tree = {}

#     for root, dirs, files in os.walk(startpath):

#         branches = [startpath]
#         if root != startpath:
#             branches.extend(os.path.relpath(root, startpath).split('/'))
#         leaf = dict([(d,{}) for d in dirs] + [(f,'file') for f in files])

#         set_leaf(tree, branches, leaf)
        
#         return tree

# def populate(tree, path):
#     full = {}
#     dir_list = []
#     full.update({'dirs': dir_list})
#     for root, dirs, files in os.walk(path, followlinks=False):
#         print(root, dirs, files)
#         # self.full.update({'dirs': dirs})
#         full.update({'root': root, 'files': files})
#         for dir in dirs:
#             fullpath = str(full['root'] + '/' + dir)
#             entry = {'name': dir, 'fullpath': fullpath}
#             full['dirs'].append(entry)
#         break
        

# def recursive(idk):
#     print(idk)
#     full = {}
#     dir_list = []
#     full.update({'dirs': dir_list})

#     print(full)
#     for root, dirs, files in os.walk(idk, followlinks=False):
#         full.update({'root': root, 'files': files})
#         if not dirs:
#             full.update()
#             return full
#         else:
#             for dir in dirs:
#                 recursive(dir)

#         break
        


def walk_dirs(data={}):
    for root, dirs, files in os.walk(data["path"]):
        list_of_dirs = []

        # if files:
            # data["files"] = files

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
