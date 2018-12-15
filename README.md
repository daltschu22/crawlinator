# crawlinator
Crawl filesystem recursively and display relevant stats that you might find useful


      usage: crawlinator.py [-h] [-f] [--old-rollup x days] [--size-histogram]
                            [-m | -c]
                            /filesysem/path

      Find stale dirs

      positional arguments:
          /filesysem/path      Filesystem path

      optional arguments:
          -h, --help           show this help message and exit

          -f                   Display sizes/times in a human friendly manner

          --old-rollup x days  Scan filesystem for directories with files older than #
                               of days

          --size-histogram     Display sizes of files in a histogram

          -m                   Use m_time instead of a_time

          -c                   Use c_time instead of a_time
