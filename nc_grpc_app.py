"""gRPC client for the netconf over outbound https"""

import random
import logging
import time
import signal
import sys
import os
import argparse
import nc_grpc_app_lib as ncg
from jnpr.junos import Device
import paho.mqtt.client as mqtt
import multiprocessing
import json

# Logging format and config
logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger('nc_grpc_main')

fileHandler = logging.FileHandler("/var/log/outbound_https.log")
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)


client_threads = {}
outbound_config_global = {}
mgmt_instance_old = 0
mgmt_instance_status = 0
MQTT_IP = ''
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TIMEOUT = 600
Default_wait_time = 30

# This function is called by the propopgate_changes function, to restart or add
# a client
def add_outbound_client(outbound_client, mgmt_status):
    global client_threads
    global outbound_config_global

    name = outbound_client['name']
    device_id = outbound_client['device-id']
    secret = outbound_client['secret']
    logger.info("Called crypt object")
    crypt_obj = ncg.JuniperEncrypter()
    secret = crypt_obj.decrypt(secret)
    logger.info("Secret is decrypted")
    servers = outbound_client['servers']
    if len(servers) == 0:
        try:
            client_threads.pop(name)
            outbound_config_global.pop(name)
            logger.info("Checking for the error")
        except Exception as e: print(e)
        return
    wait_time = Default_wait_time
    reconnect_strategy = 1
    if 'waittime' in outbound_client.keys():
        wait_time = outbound_client['waittime']
    if 'reconnect-strategy' in outbound_client.keys():
        if outbound_client['reconnect-strategy'] == "in-order":
            reconnect_strategy = 1
        elif outbound_client['reconnect-strategy'] == "sticky":
            reconnect_strategy = 2

    if not hasattr(sys.stdin, 'close'):
        def dummy_close():
            pass
        sys.stdin.close = dummy_close

    queue = multiprocessing.Queue()
    p1 = multiprocessing.Process(target=ncg.run_client, args=(device_id, secret, servers, wait_time, reconnect_strategy, mgmt_status, queue, ))
    p1.start()
    client_threads[name] = [p1, queue]
    logger.info(client_threads)
    outbound_config_global.update({outbound_client['name']:outbound_client})
    logger.info("Started new jet process {}".format(p1.pid))

# List of important config associated with the client
# Change in this list would trigger child process restart 
def imp_make_list_dict(outbound_client):
    list = []
    list.append(outbound_client['name'])
    list.append(outbound_client['device-id'])
    list.append(outbound_client['secret'])
    servers = outbound_client['servers']

    for server in servers:
        list.append(server['name'])
        list.append(server['trusted-cert'])
        if 'port' in server.keys():
            list.append(server['port'])
        else:
            list.append(443)

    return list

# List of non-important config associated with the client
# Change in this list would not trigger child process restart
def nimp_make_list_dict(outbound_client):
    list = []
    if 'waittime' in outbound_client.keys():
        list.append(outbound_client['waittime'])
    else:
        list.append(Default_wait_time)
    if 'reconnect-strategy' in outbound_client.keys():
        if outbound_client['reconnect-strategy'] == "in-order":
            list.append(1)
        elif outbound_client['reconnect-strategy'] == "sticky":
            list.append(2)
    else:
        list.append(1)

    return list


# Removes the inactive elements in the config
def remove_inactive(clients):
    clients_updated = []
    for client in clients:
        new_client = client.copy()
        if '@' in client.keys() and 'inactive' in client['@'].keys():
            continue
        if '@reconnect-strategy' in client.keys() and 'inactive' in client['@reconnect-strategy'].keys():
            del new_client["reconnect-strategy"]
        if '@waittime' in client.keys() and 'inactive' in client['@waittime'].keys():
            del new_client["waittime"]
        if 'servers' in client.keys():
            for server in client['servers']:
                if '@' in server.keys() and 'inactive' in server['@'].keys():
                    new_client['servers'].remove(server)
        else:
            new_client['servers'] = []
        clients_updated.append(new_client)
    logger.info("Remove inactive config function executed properly")
    return clients_updated


def is_there_any_change(outbound_client, outbound_client_old):
    list_old_imp = imp_make_list_dict(outbound_client_old)
    list_new_imp = imp_make_list_dict(outbound_client)

    list_old_nimp = nimp_make_list_dict(outbound_client_old)
    list_new_nimp = nimp_make_list_dict(outbound_client)
    if (set(list_old_imp) == set(list_new_imp) and set(list_old_nimp) == set(list_new_nimp) ):
        logger.info("Propagation_phase: No change in the objects")
        return 0
    elif (set(list_old_imp) == set(list_new_imp) and set(list_old_nimp) != set(list_new_nimp)):
        logger.info("Propagation_phase: Change in the non important objects, restart not required")
        return 1
    else:
        logger.info("Propagation_phase: Change in important objects, restart required ")
        return 2


# Check whether there is any change management instance
def is_there_any_change_in_mgmt():
    global mgmt_instance_status
    global mgmt_instance_old
    if mgmt_instance_status == mgmt_instance_old:
        return 0
    else:
        mgmt_instance_old = mgmt_instance_status
        return 1

# This function takes care of adding new clients if there is a new client added
# in the configuration
# Also takes care of deleting, restarting the existing clients, if there is any config change
def propagate_changes(outbound_config_new):
    global client_threads
    global outbound_config_global
    global mgmt_instance_status
    global mgmt_instance_old

    client_threads_check_flags = []

    for outbound_client in outbound_config_new:

        logger.info("Propagation_phase: checking for the changes in the client")
        if outbound_client['name'] in client_threads.keys():
            outbound_client_old = outbound_config_global[outbound_client['name']]
            # Check whether the object is changed
            is_there_change_value  = is_there_any_change(outbound_client, outbound_client_old)
            if(is_there_change_value == 2 or is_there_any_change_in_mgmt()):
                # Change in important config, restart required
                logger.info("Propagation_phase: change in client restarting {} client".format(outbound_client['name']))
                p = client_threads[outbound_client['name']][0]
                try:
                    os.kill(p.pid, signal.SIGTERM)
                except:
                    pass
                add_outbound_client(outbound_client, mgmt_instance_status)
            elif(is_there_change_value == 1):
                # Change in non-important config, let the child process know through multiprocess queue
                q = client_threads[outbound_client['name']][1]
                q.put(outbound_client)
                outbound_config_global.update({outbound_client['name']:outbound_client})
            else:
                # No change in the objects
                logger.info("Propagation_phase: No change in the {} client".format(outbound_client['name']))
                pass
        else:
            # It means a new client is added
            logger.info("Propagation_phase: new client {} client".format(outbound_client['name']))
            add_outbound_client(outbound_client, mgmt_instance_status)
        client_threads_check_flags.append(outbound_client['name'])

    logger.info("Propagation_phase: addition and changing of the clients is successful")

    # Now check for deletion
    client_threads_iter = client_threads.copy()
    for client_thread_name in client_threads_iter.keys():
        if client_thread_name not in client_threads_check_flags:
            logger.info("Propagation_phase: deleting {} client".format(client_thread_name))
            p = client_threads_iter[client_thread_name][0]
            try:
                os.kill(p.pid, signal.SIGTERM)
            except:
                pass
            try:
                client_threads.pop(client_thread_name)
                outbound_config_global.pop(client_thread_name)
                logger.info("checking for the error")
            except Exception as e: print(e)

    logger.info("Propagation_phase: propagation of the new config ended")


# Fetches the outbound https configuration and also removes the inactive active
# while return the config
def get_outbound_https_config():
    global mgmt_instance_status
    dev = Device(host='localhost')
    dev.open()
    data_main = dev.rpc.get_config(filter_xml='system', options={'inherit':'inherit', 'format':'json', 'database' : 'committed'})
    dev.close()

    if 'system' in data_main['configuration'].keys():
        if 'management-instance' in data_main['configuration']['system'].keys():
            mgmt_instance_status = 1
        else:
            mgmt_instance_status = 0

        if 'services' in data_main['configuration']['system'].keys():
            data_services = data_main['configuration']['system']['services']
            if '@' in data_services.keys() and 'inactive' in data_services['@'].keys():
                return []

            if 'outbound-https' in data_main['configuration']['system']['services'].keys():
                data = data_main['configuration']['system']['services']['outbound-https']
                logger.info(data)
                if '@' in data.keys() and 'inactive' in data['@'].keys():
                    return []
                if 'client' in data.keys():
                    return remove_inactive(data['client'])

    return []


# on_connect function is executed when the this app is connected to mqtt client
def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code {}".format(rc))
    outbound_config = get_outbound_https_config()
    logger.info("MQTT_on_connect: Outbound config received, feeding it to propagate changes")
    propagate_changes(outbound_config)
    client.subscribe("/junos/events/genpub/+", 1)


# on_message function is executed whenever there's a commit in mgd
def on_message(client, userdata, msg):
    check_str = json.loads(msg.payload.decode())['commit-patch']
    logger.info(check_str)
    if "outbound-https" in check_str or "management-instance" in check_str or "apply-groups" in check_str:
        outbound_config_new = get_outbound_https_config()
        logger.info("on_message: propagate changes for the new config is called")
        propagate_changes(outbound_config_new)

    logger.info("MQTT: On message function executed")


def run():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info("MQTT client is created and ready to connect")
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_TIMEOUT)
    logger.info("Connected to the MQTT_HOST")

    client.loop_forever()


def signal_handler(sig, frame):
    logger.info("Signal handler function invoked")
    global main_process_pid
    global client_threads
    if os.getpid() == main_process_pid:
        logger.info("Kill called from the main process")
        logger.info(client_threads)
        for p_key in client_threads.keys():
            try:
                os.kill(client_threads[p_key][0].pid, signal.SIGTERM)
            except:
                pass
        os.kill(main_process_pid, signal.SIGKILL)

    term = ncg.term
    clients = ncg.clients
    term = 1
    logger.info("Entered into the signal handler")
    for client in clients:
        proc = client.proc
        channel = client.channel
        if proc != 0:
            logger.info("Killing the proc")
            try:
                proc.stdin.close()
                proc.stdout.close()
            except:
                pass
            try:
                proc.terminate()
            except:
                pass
            term = 1

        logger.info("Killing the grpc client")
        channel.close()

    logger.info("About to kill the app")
    os.kill(os.getpid(), signal.SIGKILL)


if __name__ == '__main__':
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main_process_pid = os.getpid()

    logger.info("Creating mqtt client")
    run()
