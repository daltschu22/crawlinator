import os
from . import file_apps

def walk_dir(dir_path):
    """Returns a tuple of the root path, list of dirs, and list of files"""
    for root, dirs, files in os.walk(dir_path):
        break

    return root, dirs, files

def process_directory(og_path, redis, queues):
    """Returns a tuple of the root path, list of dirs, and list of files"""
    root, directory_list, file_list = walk_dir(og_path)

    dir_queue = queues.get('dir_queue')

    # Increment the amount of directories discovered
    redis.incr('stats:TotalDirs', len(directory_list))

    for directory in directory_list:
        os.path.join(root, directory)
        dir_queue.enqueue(process_directory, directory)