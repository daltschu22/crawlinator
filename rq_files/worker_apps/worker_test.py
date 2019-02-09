def add_nums(input_list):
    final_num = 0
    for item in input_list:
        final_num += final_num + item

    return final_num