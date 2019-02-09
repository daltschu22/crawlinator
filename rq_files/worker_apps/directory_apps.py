import os
from . import file_apps

def walk_dir(dir_path):
    """Returns a tuple of the root path, list of dirs, and list of files"""
    for root, dirs, files in os.walk(dir_path):
        break

    return root, dirs, files

def process_directory(redis, queues, og_path):
    """Returns a tuple of the root path, list of dirs, and list of files"""
    root, directory_list, file_list = walk_dir(og_path)

    dir_queue = queues.get('dir_queue')

    # Increment the amount of directories discovered
    redis.incr('stats:TotalDirs', len(directory_list))
    redis.incr('stats:TotalFiles', len(file_list))

    print("List of dirs {}".format(directory_list))

    for directory in directory_list:
        print("Processing directory {}".format(directory))
        full_path = os.path.join(root, directory)
        dir_queue.enqueue_call(
            func=process_directory, 
            args=(redis,
            queues,
            full_path
            )
        )

