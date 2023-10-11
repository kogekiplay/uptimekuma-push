import socket
import requests
import time
import configparser
import json
import syslog

# Open the syslog connection
syslog.openlog(facility=syslog.LOG_DAEMON)

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

# get api url
api_base_url = config.get('API', 'url')
sleep_duration = int(config.get('API', 'interval'))


def ping(target_name, target_host, target_port):
    try:
        start_time = time.time()
        socket.create_connection((target_host, target_port), timeout=5)
        end_time = time.time()
        ping_time = int((end_time - start_time) * 1000)
        return ping_time
    except (socket.timeout, ConnectionRefusedError):
        return -1

while True:
    # 遍历所有的目标组
    for section in config.sections():
        if section.startswith('TARGET'):
            target_name = config.get(section, 'name')
            target_host = config.get(section, 'host')
            target_port = int(config.get(section, 'port'))
            api_token = config.get(section, 'token')

            # 构建完整的API URL
            api_url = f'{api_base_url}/{api_token}'

            # 执行Ping函数
            ping_result = ping(target_name,target_host, target_port)

            # 准备要发送的数据
            data = {
                'status': 'up' if ping_result > 0 else 'down',
                'msg': 'Online' if ping_result > 0 else 'Offline',
                'ping': ping_result
            }

            # 发送HTTP请求
            response = requests.get(api_url, params=data)

            output_data = {
                'name': target_name,
                'ping_result': ping_result,
                'response': response.json(),  # Assuming the response is in JSON format
                'time': time.strftime("%Y.%m.%d %H:%M:%S", time.localtime())
            }
            output_json = json.dumps(output_data, ensure_ascii=False)
            # 输出响应内容
            syslog.syslog(syslog.LOG_INFO, output_json)

    time.sleep(sleep_duration)
