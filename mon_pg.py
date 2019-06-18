#!/usr/bin/env python
# coding:utf-8
'''
@author: lcrash
@time: 2019/4/3
@desc: 检测Postgresql数据库主从状态，如果主库发生意外宕机等，进行FailOver
       检测所在机器，打通postgresql所使用用户的ssh，这样方便发送命令
       为方便只支持规范部署的同用户和同安装目录的方式
       要求启动postgres命令必须带路径启动pg_ctl start -D $pgdatadir
       脚本使用pgdatadir结尾不能带/ 因为pg_ctl启动起来过后会自动去除末尾/
       增加企信报警
       增加VIP方式切换，DNS业务方缓存时间有问题，ip/arping命令必须提供chmod u+s，否则无法执行
       增加检测要防止网络抖动功能,多次异常才能使用切换命令
       增加异常打印到日志
       本脚本的监控需要用到其他调度平台，比如JOBX做任务监控
       如果出现SSHException: Incompatible ssh peer 检测机器需要升级paramiko模块版本 pip install paramiko --upgrade 不升级可能导致判断错误
'''

import argparse
import sys
import logging
import paramiko
import time
from notify import notifyQixin


def parse_args():
    parser = argparse.ArgumentParser(description='Parse', add_help=False)
    config = parser.add_argument_group(
        '### postgres failover configuration ###')
    config.add_argument('--pgmaster', type=str,
                        help='set postgres instance MASTER ip', default='')
    config.add_argument('--pgslave', type=str,
                        help='set postgres instance SLAVE ip', default='')
    config.add_argument('--sshport', type=int,
                        help='set ssh port', default=22)
    config.add_argument('--pgport', type=int,
                        help='set postgres instance port', default=5432)
    config.add_argument('--pgbindir', type=str,
                        help='set pg_controldata dir', default='/usr/local/pgsql/bin')
    # pg_ctl 启动过后会把datadir启动去除末尾/, 所以这里不能/ 结尾
    config.add_argument('--pgdatadir', type=str,
                        help='set postgres instance data dir, Dont end with /', default='')
    config.add_argument('--pgusername', type=str,
                        help='set postgresql instance username', default='postgres')
    config.add_argument('--vip', type=str,
                        help='set postgresql instance vip', default='')
    parser.add_argument('-help', '--help', dest='help',
                        action='store_true', help='help information', default=False)
    return parser


def commandline_args(args):
    need_print_help = False if args else True
    parser = parse_args()
    args = parser.parse_args(args)
    if args.help or need_print_help:
        parser.print_help()
        sys.exit(1)
    if not args.pgmaster:
        raise ValueError('Lack of parameter: pgmaster')
    if not args.pgslave:
        raise ValueError('Lack of parameter: pgslave')
    if not args.sshport:
        raise ValueError('Lack of parameter: sshport')
    if not args.pgport:
        raise ValueError('Lack of parameter: pgport')
    if not args.pgbindir:
        raise ValueError('Lack of parameter: pgbindir')
    if not args.pgdatadir:
        raise ValueError('Lack of parameter: pgdatadir')
    if not args.pgusername:
        raise ValueError('Lack of parameter: pgusername')
    if not args.vip:
        raise ValueError('Lack of parameter: vip')
    return args


def ssh_cmd(host, port, cmd, username):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, port=port, username=username, timeout=5)
        stdin, stdout, stderr = ssh.exec_command(cmd)
        res = stdout.readlines()
        ssh.close()
    except Exception as e:
        # res = [0] 提前，规避异常之后不能正常进行，必须报错No existing session
        res = [0]
        str_exception = 'ssh cmd exception:: '+str(e)
        logger(str_exception)
        notifyQixin(str_exception)
    return res


def logger(msg):
    logging.basicConfig(format='%(asctime)s %(message)s',
                        filename='mon_postgres_ha.log', level=logging.WARNING)
    logging.warning(msg)


class Pg_failover_obj(object):
    def __init__(self, pgmaster, pgslave, sshport, pgport, pgbindir, pgdatadir, pgusername, vip):
        self.pgmaster = pgmaster
        self.pgslave = pgslave
        self.sshport = sshport
        self.pgport = pgport
        self.pgbindir = pgbindir
        self.pgdatadir = pgdatadir
        self.pgusername = pgusername
        self.vip = vip

    # 检查实例存活和角色
    def check_status(self, host):
        # 判断实例存活状态
        # 要求启动postgres命令必须是pg_ctl start -D $pgdatadir，否则这里检测不到
        cmd_alive = 'ps aux|grep "postgres -D %s"|grep -v grep|wc -l' % self.pgdatadir
        res_alive = ssh_cmd(host, self.sshport, cmd_alive, self.pgusername)
        str_alive = res_alive[0]
        # 判断实例的真实role, str_alive:0 实例关闭，1：实例打开
        chk_role = ''
        if int(str_alive) == 1:
            # 主机的cluster state是in production，备机的cluster state是in archive recovery
            cmd_role = '%s/pg_controldata -D %s|grep cluster' % (self.pgbindir, self.pgdatadir)
            res_role = ssh_cmd(host, self.sshport, cmd_role, self.pgusername)
            str_res_role = res_role[0].split(':')[1]
            if 'in production' in str_res_role:
                chk_role = 'master'
            elif 'in archive recovery' in str_res_role:
                chk_role = 'slave'
        elif int(str_alive) == 0:
            chk_role = 'close'
        return int(str_alive), chk_role

    # 更改VIP函数
    def change_vip(self):
        # 可能是异构环境，所以下面的可能需要更改代码
        # 网卡名bond0 根据实际情况更改
        # ip/arping命令必须提供chmod u+s，否则无法执行
        cmd_ip_del = 'ip addr del %s dev eno1 &>/dev/null' % self.vip
        ssh_cmd(self.pgmaster, self.sshport, cmd_ip_del, self.pgusername)
        cmd_ip_add = 'ip addr add %s dev eno1 &>/dev/null' % self.vip
        ssh_cmd(self.pgslave, self.sshport, cmd_ip_add, self.pgusername)
        # arping要根据系统更改（下面的参数根据系统和arping版本不一致都有区别，最好提前验证命令）,网关根据实际情况更改
        cmd_arping = '/usr/sbin/arping -c 3 -U -i eno1 -S %s 10.6.11.254 &>/dev/null' % self.vip
        ssh_cmd(self.pgslave, self.sshport, cmd_arping, self.pgusername)

    # 切换函数
    def failover_instance(self):
        # 要发起杀pg实例的命令，无论是否可以ping通挂掉实例
        # 先通过pg命令杀进程，预留一分钟，再执行操作系统杀进程
        cmd_pg_kill_master = '%s/pg_ctl stop -D %s -m f' % (self.pgbindir, self.pgdatadir)
        ssh_cmd(self.pgmaster, self.sshport,cmd_pg_kill_master, self.pgusername)
        logger('MON_PG:: FAILOVER:: kill old master and wait 60 seconds!')
        time.sleep(60)
        cmd_kill_master = 'ps aux|grep "postgres -D %s"|grep -v grep|awk \'{print $2}\'|xargs kill -9' % self.pgdatadir
        ssh_cmd(self.pgmaster, self.sshport, cmd_kill_master, self.pgusername)
        log_text_kill_old_master = 'MON_PG:: FAILOVER:: kill old master %s@%s!' % (self.pgmaster, self.pgdatadir)
        logger(log_text_kill_old_master)
        notifyQixin(log_text_kill_old_master)
        # 提升从库为主库
        cmd_promote = '%s/pg_ctl promote -D %s' % (self.pgbindir, self.pgdatadir)
        ssh_cmd(self.pgslave, self.sshport, cmd_promote, self.pgusername)
        log_text_promote_new_master = 'MON_PG:: FAILOVER:: promote new master %s@%s!' % (
            self.pgslave, self.pgdatadir)
        logger(log_text_promote_new_master)
        notifyQixin(log_text_promote_new_master)
        # 调用vip漂移功能
        self.change_vip()
        log_text_change_vip = 'MON_PG:: FAILOVER:: changed vip done!'
        logger(log_text_change_vip)
        notifyQixin(log_text_change_vip)
        sys.exit(0)

    # 判断结果的role是否跟指定的role一致
    def judge(self):
        # 异常需要切换的增加判断次数到连续10次才采取操作
        # 检测要防止网络抖动，连续出现10次则做failover处理，如果中途通一次则需要清零计数器
        chk_cnt = 0
        while True:
            alive_master, real_master = self.check_status(self.pgmaster)
            alive_slave, real_slave = self.check_status(self.pgslave)
            # alive:0 实例关闭，1：实例打开
            if alive_slave == 1:
                if alive_master == 1:
                    if real_master == 'master' and real_slave == 'slave':
                        logger('MON_PG:: JUDGE:: everything is OK!')
                        time.sleep(3)
                        chk_cnt = 0
                    # 异常逻辑-主库错误后恢复，同时存在了两个主库，人工干预，不停的发消息到企信
                    elif real_master == 'master' and real_slave == 'master':
                        log_text_same_up = 'MON_PG:: JUDGE:: master %s:%s and slave %s:%s are same master' % (
                            self.pgmaster, self.pgport, self.pgslave, self.pgport)
                        logger(log_text_same_up)
                        notifyQixin(log_text_same_up)
                        time.sleep(3)
                        chk_cnt = 0
                    # 异常逻辑-已经切换需要重新配置脚本输入
                    elif real_master == 'slave' and real_slave == 'master':
                        logger(
                            'MON_PG:: JUDGE:: wrong master and slave! check your inputs!')
                        break
                # 异常逻辑-主库宕机
                elif alive_master == 0:
                    if chk_cnt == 10:
                        self.failover_instance()
                        # logger('测试输出：进入failover')
                        # break
                    else:
                        log_text_master_down = 'MON_PG:: JUDGE:: master down check times %s!' % chk_cnt
                        logger(log_text_master_down)
                        chk_cnt += 1
                        time.sleep(3)
            # 异常逻辑-从库不通无法切换
            elif alive_slave == 0:
                logger('MON_PG:: JUDGE:: can not judge postgres HA!')
                time.sleep(3)


if __name__ == '__main__':
    args = commandline_args(sys.argv[1:])
    pg_failover_obj = Pg_failover_obj(pgmaster=args.pgmaster,  pgslave=args.pgslave, sshport=args.sshport,
                                      pgport=args.pgport, pgbindir=args.pgbindir, pgdatadir=args.pgdatadir,
                                      pgusername=args.pgusername, vip=args.vip)
    pg_failover_obj.judge()
