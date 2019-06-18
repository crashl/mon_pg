# mon_pg

说明：
自己写的一个监控postgres流赋值的脚本，简单HA

用法：
1.直接执行mon_pg.py
2.借助其他调度平台（如JOBX）调用chk_mon_pg_alive.py，定时扫描脚本是否健康，并使用企业微信报警（notify.py）
