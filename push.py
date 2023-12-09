import socket
import requests
import configparser
import json
import syslog
import logging
import schedule
import time
from collections import deque

# Open the syslog connection
syslog.openlog(facility=syslog.LOG_DAEMON)
# 配置日志记录器
logging.basicConfig(
    filename='log/output.log', level=logging.INFO)

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')


def ping(target_host, target_port):
    try:
        start_time = time.time()
        socket.create_connection((target_host, target_port), timeout=5)
        end_time = time.time()
        ping_time = int((end_time - start_time) * 1000)
        return ping_time
    except (socket.timeout, ConnectionRefusedError):
        return -1
    except socket.gaierror as e:
        syslog.syslog(syslog.LOG_ERR,
                      f"DNS resolution error for {target_host}: {e}")
        logging.error(f"DNS resolution error for {target_host}: {e}")
        return -1


def send_data(target_name, target_host, target_port, api_token, api_base_url, dns_token, zone_id, domain, target_cnames):
    ping_result = ping(target_host, target_port)

    # Prepare the data to be sent
    data = {
        'status': 'up' if ping_result > 0 else f'离线，正在尝试切换Cname域名，当前CNAME: {target_cnames[0] if target_cnames and len(target_cnames) > 0 else "无"}, 下一个CNAME: {target_cnames[1] if target_cnames and len(target_cnames) > 1 else "无"}',
        'msg': 'Online' if ping_result > 0 else 'Online',
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
        logging.info(output_json)

        if ping_result < 0 and target_cnames and dns_token and zone_id and domain:
            dns_id = get_record_id(zone_id, domain, dns_token)

            # Check if DNS record ID retrieval was successful
            if dns_id is None:
                syslog.syslog(
                    syslog.LOG_ERR, "Failed to retrieve DNS record ID. Skipping CNAME switch.")
                logging.error(
                    "Failed to retrieve DNS record ID. Skipping CNAME switch.")
                return

            # Switch to the next CNAME in the list
            new_cname = target_cnames.popleft()
            target_cnames.append(new_cname)

            # Update DNS record with the new CNAME
            update_success = update_dns_record(
                zone_id, domain, dns_token, dns_id, new_cname, ttl=60)
            if not update_success:
                syslog.syslog(
                    syslog.LOG_ERR, f"Failed to update DNS record with new CNAME: {new_cname}")
                logging.error(
                    f"Failed to update DNS record with new CNAME: {new_cname}")

    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f"An error occurred: {e}")
        logging.error(f"An error occurred: {e}")


def get_record_id(zone_id, domain_name, dns_token):
    if not dns_token or not zone_id:
        return None

    resp = requests.get(
        'https://api.cloudflare.com/client/v4/zones/{}/dns_records'.format(
            zone_id),
        headers={
            'Authorization': 'Bearer ' + dns_token,
            'Content-Type': 'application/json'
        })
    if not json.loads(resp.text)['success']:
        return None
    domains = json.loads(resp.text)['result']
    for domain in domains:
        if domain_name == domain['name']:
            return domain['id']
    return None


def update_dns_record(zone_id, domain, dns_token, dns_id, content, ttl, proxied=False):
    if not dns_token or not zone_id:
        return False

    resp = requests.put(
        'https://api.cloudflare.com/client/v4/zones/{}/dns_records/{}'.format(
            zone_id, dns_id),
        json={
            'type': 'CNAME',
            'name': domain,
            'content': content,
            'ttl': ttl,
            'proxied': proxied
        },
        headers={
            'Authorization': 'Bearer ' + dns_token,
            'Content-Type': 'application/json'
        })
    if not json.loads(resp.text)['success']:
        return False
    return True


def get_target_config(section):
    return (
        config.get(section, 'name'),
        config.get(section, 'host'),
        int(config.get(section, 'port')),
        config.get(section, 'token'),
        config.get('API', 'url'),
        config.get('API', 'dns_token', fallback=None),
        config.get(section, 'zoneid', fallback=None),
        config.get(section, 'domain', fallback=None),
        deque(config.get(section, 'cnames', fallback='').split(',')) or None
    )


def schedule_tasks():
    for section in config.sections():
        if section.startswith('TARGET'):
            target_name, target_host, target_port, api_token, api_base_url, dns_token, zone_id, domain, target_cnames = get_target_config(
                section)
            sleep_duration = int(config.get('API', 'interval'))
            # Schedule the job with the function and its arguments

            # Initial call to send_data
            send_data(target_name, target_host, target_port, api_token,
                      api_base_url, dns_token, zone_id, domain, target_cnames)
            schedule.every(sleep_duration).seconds.do(
                send_data, target_name, target_host, target_port, api_token, api_base_url, dns_token, zone_id, domain, target_cnames)
            schedule.every(sleep_duration * 5 - 30).seconds.do(
                send_data, target_name, target_host, target_port, api_token, api_base_url, dns_token, zone_id, domain, target_cnames)
            # You can add more schedule.every lines if needed

# ...


def main():
    schedule_tasks()

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
