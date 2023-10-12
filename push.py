import socket
import requests
import configparser
import json
import syslog
import schedule
import time

# Open the syslog connection
syslog.openlog(facility=syslog.LOG_DAEMON)

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

# get api url

def ping(target_host, target_port):
    try:
        start_time = time.time()
        socket.create_connection((target_host, target_port), timeout=5)
        end_time = time.time()
        ping_time = int((end_time - start_time) * 1000)
        return ping_time
    except (socket.timeout, ConnectionRefusedError):
        return -1

def send_data(target_name, target_host, target_port, api_token, api_base_url):
    ping_result = ping(target_host, target_port)

    # Prepare the data to be sent
    data = {
        'status': 'up' if ping_result > 0 else 'down',
        'msg': 'Online' if ping_result > 0 else 'Offline',
        'ping': ping_result
    }

    # Construct the full API URL
    api_url = f'{api_base_url}/{api_token}'

    try:
        response = requests.get(api_url, params=data)
        response.raise_for_status()  # Check for HTTP errors

        output_data = {
            'name': target_name,
            'ping': ping_result,
            'response': response.json(),  # Assuming the response is in JSON format
            'time': time.strftime("%Y.%m.%d %H:%M:%S", time.localtime())
        }
        output_json = json.dumps(output_data, ensure_ascii=False)
        syslog.syslog(syslog.LOG_INFO, output_json)

    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f"An error occurred: {e}")

def schedule_tasks():
    for section in config.sections():
        if section.startswith('TARGET'):
            api_base_url = config.get('API', 'url')
            target_name = config.get(section, 'name')
            target_host = config.get(section, 'host')
            target_port = int(config.get(section, 'port'))
            api_token = config.get(section, 'token')
            sleep_duration = int(config.get('API', 'interval'))
            send_data(target_name, target_host, target_port, api_token, api_base_url)
            schedule.every(sleep_duration).seconds.do(send_data, target_name, target_host, target_port, api_token, api_base_url)

def main():
    schedule_tasks()

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    main()
