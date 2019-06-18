#!/usr/bin/env python
# coding:utf-8
'''
@author: lcrash
@time: 2019/4/24
@desc: 检测mon_pg.py是否正常运行，放到jobx平台调用
'''

import subprocess
import sys
import time
from notify import notifyQixin


def create_sub2(cmd):
    p = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = p.stdout.read()
    code = p.wait()
    return code, result


def chk_mon_pg_alive():
    cmd_chk = 'ps aux|grep mon_pg.py|grep -v grep|wc -l'
    code, res = create_sub2(cmd_chk)
    if int(res) == 0:
        # 这里根据脚本具体情况填输出内容
        notifyQixin('postgres高可用监控脚本没有正常运行')


if __name__ == "__main__":
    # while True:
    #     chk_mon_pg_alive()
    #     time.sleep(5)
    # 不用无限循环，直接改用jobx定时调用
    chk_mon_pg_alive()