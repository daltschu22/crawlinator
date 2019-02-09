import os

def parse_list_files(redis, queues, file_list):

    file_queue = queues.get('file_queue')
    for file in file_list:
        stat_info = stat_file(file)

def stat_file(redis, file_path):
    try:
        stat_info = os.stat(file_path)
    except Exception as e:
        error_dict = {e: file_path}
        # stats_object.stats["Failures"].append(error_dict)
        # continue

    return stat_info
        