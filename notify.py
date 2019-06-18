#!/usr/bin/env python
# coding:utf-8
'''
@author: lcrash
@time: 2019/2/21
@desc: 企信报警接口
'''

import requests
import json
import time
import sys

reload(sys)
sys.setdefaultencoding('utf-8')


class WeChat:
    def __init__(self, dictData):
        self.CORPID = dictData["corpid"]
        self.CORPSECRET = dictData["corpsecret"]
        self.AGENTID = dictData["agentid"]
        # 账号，如果是应用下的所有用户@all，如果是部份用userid1|userid2|userid2，最多1000个
        # DBA组成员的userid
        self.TOUSER = dictData["userids"]
        self.msg = dictData["msg"]

    def _get_access_token(self):
        # https: // qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=ID&corpsecret=SECRECT
        url = 'https://qyapi.weixin.qq.com/cgi-bin/gettoken'
        values = {'corpid': self.CORPID, 'corpsecret': self.CORPSECRET}
        req = requests.post(url, params=values)
        data = json.loads(req.text)
        # print data
        return data["access_token"]

    def get_access_token(self):
        try:
            with open('access_token.conf', 'r') as f:
                t, access_token = f.read().split()
        except:
            with open('access_token.conf', 'w') as f:
                access_token = self._get_access_token()
                cur_time = time.time()
                f.write('\t'.join([str(cur_time), access_token]))
                return access_token
        else:
            cur_time = time.time()
            if 0 < cur_time - float(t) < 7260:
                return access_token
            else:
                with open('access_token.conf', 'w') as f:
                    access_token = self._get_access_token()
                    f.write('\t'.join([str(cur_time), access_token]))
                    return access_token

    def send_data(self, message):
        send_url = 'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=' + self.get_access_token()
        # 在Python中这样定义为字典，需用json.dumps转换成json对象，否则提示msgtype类型错误，转为不是Json对象
        send_data_json = json.dumps(
            {"touser": self.TOUSER, "msgtype": "text", "agentid": self.AGENTID, "text": {"content": message},
             "safe": 0})
        r = requests.post(send_url, send_data_json)
        return r.content


def notifyQixin(msg):
    dictData = {"corpid": "xxxx", "corpsecret": "xxxx",
                "agentid": "100000", "userids": "@all", "msg": '%s' % msg}
    wx = WeChat(dictData)
    wx.send_data(wx.msg)


if __name__ == '__main__':
    msgStr = sys.argv[1:]
    msg = " ".join(msgStr)
    notifyQixin(msg)
    # python notify.py 'change vip done'
