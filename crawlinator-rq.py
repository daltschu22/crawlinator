#!/usr/bin/env python

# import sys
import os
import argparse
import pprint
import time
import checkpyversion
from redis import Redis
from rq import Worker, Queue, Connection
import rq_files.worker_apps.directory_apps as dir_apps
import rq_files.worker_apps.file_apps as file_apps

#MAKE SURE TO RUN `rq worker test` IN THE FOLDER THIS SCRIPT IS IN

redis = Redis(host='localhost')

pp = pprint.PrettyPrinter(indent=4)

epoch_one_day = 86400
current_epoch = time.time()

worker_count = 10

def parse_arguments():
    parser = argparse.ArgumentParser(description="Crawl filesystem using workers and queues")
    parser.add_argument('path', metavar='/filesysem/path', help="Filesystem path")

    return parser.parse_args()

# def spinup_workers(q):
#     with Connection(connection=redis):
#         [Worker(q).work() for i in range(worker_count)]

def check_read_perms(path):
    """Check permissions of a path"""
    access = os.access(path, os.R_OK)

    return access

def main():
    args = parse_arguments() #Parse arguments

    main_path = args.path

    # path_perms = check_read_perms(main_path)
    # if not path_perms:
    #     print("You dont have permission, or that path doesnt exist!")
    #     exit()

    queues = {}
    queues['dir_queue'] = Queue('dirs', connection=redis)
    queues['file_queue'] = Queue('files', connection=redis)
    
    queues['dir_queue'].empty()
    queues['file_queue'].empty()

    redis.set('stats:TotalFiles', 0)
    redis.set('stats:TotalDirs', 1)
    redis.set('stats:TotalSize', 0)

   
    # queues.get('dir_queue').enqueue_call(
    #     func=dir_apps.process_directory, 
    #     args=(redis, fs_dict)
    # )

    # dir_list, file_list = dir_apps.process_directory(redis, main_path)



    time.sleep(3)

    TotalDirs = redis.get('stats:TotalDirs')
    TotalFiles = redis.get('stats:TotalFiles')
    print("There were {} dirs".format(TotalDirs))
    print("There were {} files".format(TotalFiles))
    # print(redis.get('stats:TotalSize'))




    # job1 = q.enqueue(add_nums, [1, 2, 3])
    # job2 = q.enqueue(add_nums, [5, 5, 5])


    # time.sleep(2)
    # print(job1.result, job2.result)



if __name__ == "__main__":
    main()


