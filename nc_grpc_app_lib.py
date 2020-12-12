"""gRPC client library for the netconf over outbound https"""

import random
import logging
import time
import signal
import sys
import os
import argparse
import subprocess
import select
import threading
import re
from fcntl import fcntl, F_GETFL, F_SETFL
from os import O_NONBLOCK, read

import jcs
import grpc

import jnx_netconf_service_pb2 as nc_grpc_pb2
import logging


# Logging format and config
logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger('nc_grpc_lib')

fileHandler = logging.FileHandler("/var/log/outbound_https.log")
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)


# global space
term = 0
clients = []
mgmt_status_client = 0

# Used to decode the $9 encoded secret keys
class JuniperEncrypter():
    MAGIC = "$9$"
    FAMILY = ["QzF3n6/9CAtpu0O", "B1IREhcSyrleKvMW8LXx", "7N-dVbwsY2g4oaJZGUDj", "iHkq.mPf5T"]
    EXTRA = {}

    NUM_ALPHA = ""
    ALPHA_NUM = {}

    srand = random.SystemRandom()
    ENCODING = [[1,4,32], [1,16,32], [1,8,32], [1,64], [1, 32], [1,4,16,128], [1,32,64]]

    def __init__(self):
        i = 0
        for i in range(len(self.FAMILY)):
            token = self.FAMILY[i]
            for c in list(token):
                self.EXTRA.update({c: 3 - i})
        for entry in self.FAMILY:
            self.NUM_ALPHA =  self.NUM_ALPHA + entry

        i = 0
        while i < len(self.NUM_ALPHA):
            self.ALPHA_NUM.update({self.NUM_ALPHA[i]: i})
            i += 1

    def isEncryptedkey(self, key):
        if key.startswith(self.MAGIC):
            return True
        else:
            return False

    def randc(self, c):
        retVal = ""
        while c > 0:
            c -= 1
            randomIndex = self.srand.randint(0, len(self.NUM_ALPHA)-1)
            retVal += self.NUM_ALPHA[randomIndex]
        return retVal

    def gapEncode(self, p, prev, encode):
        retVal = ""
        ord_c = ord(p)
        gaps = []
        i = len(encode) - 1
        while i >= 0:
            t = int(ord_c / encode[i])
            gaps.insert(0, t)
            ord_c %= encode[i]
            i -= 1
        for gap in gaps:
            gap += self.ALPHA_NUM[prev] + 1
            c = self.NUM_ALPHA[gap % (len(self.NUM_ALPHA))]
            prev = c
            retVal += c
        return retVal

    def gap(self, c1, c2):
        gap = self.ALPHA_NUM[c2] - self.ALPHA_NUM[c1]
        retVal = 0
        if gap < 0:
            retVal = len(self.NUM_ALPHA) - (gap * -1) - 1
        else:
            # # # print(len(self.NUM_ALPHA))
            retVal = (self.ALPHA_NUM[c2] - self.ALPHA_NUM[c1]) % len(self.NUM_ALPHA) - 1
        return retVal

    def gapDecode(self, gaps, decode):
        num = 0
        i = 0
        while i < len(gaps):
            num += int(gaps[i]) * decode[i]
            i += 1
        num = num % 256
        return str(chr(num))

    def encrypt(self, inadd):
        salt = self.randc(1)
        rand = self.randc(self.EXTRA[salt[0]])
        pos = 0
        prev = salt[0]
        encrypt = self.MAGIC + salt + rand
        for p in list(inadd):
            encode = self.ENCODING[pos % (len(self.ENCODING))]
            encrypt += self.gapEncode(p, prev, encode)
            prev = encrypt[len(encrypt) - 1]
            pos += 1

        return encrypt

    def decrypt(self, encrypted):
        if not encrypted.startswith(self.MAGIC):
            raise IllegalArgumentException("Invalid encryption string")
        encrypted = encrypted[3:]
        #  trimming of the MAGIC
        first = encrypted[0:1]
        encrypted = encrypted[1:]
        encrypted = encrypted[self.EXTRA[first[0]]:]
        prev = first[0]
        plain = ""
        while encrypted != "":
            decode = self.ENCODING[ len(plain) % len(self.ENCODING)]
            nibble = encrypted[0:len(decode)]
            encrypted = encrypted[len(decode):]
            gaps = []
            for c in list(nibble):
                gap = self.gap(prev, c)
                gaps.append(gap)
                prev = c
            plain += self.gapDecode(gaps, decode)
        return plain


def make_message(message_in):
    return nc_grpc_pb2.NcgrpcCommandGetRequest(
        message = message_in
    )


# This is one of the core function for this application, which reads from the
# subprocess and sends the data to the grpc server
def generate_messages(input_proc, channel, session_type_str):

    input_des = input_proc.stdout

    # Add the read descriptors to the read descriptor list
    rdescriptors = [input_des]
    wdescriptors = []
    xdescriptors = []

    if session_type_str == "csh":
        yield(make_message("csh session is started"))

    while True:
        # If termination signal is received, yield the last message and
        # break out of the loop
        if term==1:
            input_proc.stdin.close()
            input_proc.stdout.close()
            input_proc.terminate()
            logger.info("Generation function received term==1")
            yield(make_message("Client is stopping, termination received"))
            break


        # checking whether subprocess is running or crashed
        poll = input_proc.poll()
        if poll == None:
            logger.info("Subprocess is running")
            pass
        else:
            logger.info("Subprocess not running, netconf/mgd is down, please restart it\
                        client is terminating")
            # is_subprocess_running = 0
            yield(make_message("Client is stopping, subprocess not running"))
            try:
                input_proc.stdin.close()
                input_proc.stdout.close()
                input_proc.terminate()
                logger.info("Closed the input descriptors and terminated the proc")
            except:
                logger.info("Couldn't close input descriptors or couldn't terminate the proc")

            break

        # Wait for read condition in a select call, if the stdout of the
        # subprocess spawned is readable, then the control comes out
        # of the select call
        try:
            logger.info("Waiting to read----just before select call")
            rlist, wlist, xlist = select.select(rdescriptors, wdescriptors, xdescriptors)
            logger.info("File is readable now, proceeding to read---just after the select call")
        except:
            logger.info("Select call failed, message generation is stopped, maybe termination command received")
            yield(make_message("Client is stopping, select call failed"))
            try:
                input_proc.stdin.close()
                input_proc.stdout.close()
                input_proc.terminate()
                logger.info("Closed the input descriptors and terminated the proc")
            except:
                logger.info("Couldn't close input descriptors or couldn't terminate the proc")
            break

        # Now the process.stdout is readable
        # Making the stdout non blocking for reading
        flags = fcntl(input_des, F_GETFL) # get current p.stdout flags
        fcntl(input_des, F_SETFL, flags | O_NONBLOCK)

        for read_des in rlist:
            if read_des == input_des:
                logger.info("Going to read input in while loop")
                while True:
                    try:
                        read_in = read(input_des.fileno(), 1024)
                        read_in_decoded = read_in.decode('ascii')
                        if read_in_decoded == "":
                            logger.info("read_in_decoded from the sub proc is null")
                            break
                        logger.info(read_in_decoded)
                        # Now transmit the rpc reply to the server
                        yield(make_message(read_in_decoded))
                    except OSError:
                        # the os throws an exception if there is no data
                        # # print '[No more data]'
                        break


# Each connection will have a this class object created
class nc_grpc_app:
    proc = 0
    channel = 0
    client_running = 0
    client_end = 0
    server_down = 0
    meta_data = []

    def __init__(self, device, secret_key, trusted_certs_input, port, client_name):
        logger.info("***************************Constructor called, ncgrpc class constructed*************************************")
        self.device = device
        self.secret_key = secret_key
        self.trusted_certs_input = trusted_certs_input
        self.port = port
        self.client_name = client_name
        self.meta_data = []
        self.proc = 0
        self.channel = 0
        self.client_running = 0
        self.client_end = 0
        self.server_down = 0


    def receive_cmds(self, stub, session_type_num):
        logger.info("Receive commands function called, creating netconf or csh subprocess")

        if session_type_num == 1:
            self.proc = subprocess.Popen(["netconf", "interactive"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Started netconf subprocess")
            responses = stub.NcgrpcCommandGet(generate_messages(self.proc, self.channel, "netconf"),
                                               metadata= tuple(self.meta_data))

        elif session_type_num == 2:
            self.proc = subprocess.Popen(["csh"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Started csh subprocess")
            responses = stub.NcgrpcCommandGet(generate_messages(self.proc, self.channel, "csh"),
                                               metadata= tuple(self.meta_data))

        self.client_running = 1        # This is the trigger point for another session request to be sent
        self.meta_data = []

        for response in responses:
            if term==1 :
                logger.info("termination signal Received")
                break
            logger.info("Inside responses")
            if response.kill_signal != 0:
                try:
                    self.proc.stdin.close()
                    self.proc.stdout.close()
                except:
                    pass
                try:
                    self.proc.terminate()
                except:
                    pass


            elif response.csh_command:
                logger.info((str(response.csh_command)))
                logger.info(type(str(response.csh_command)))
                str_in = str(response.csh_command)
                if re.match('^exit\s*\s*\d*?$', str_in.strip()) or re.match('^exit\s*\(\s*\d*\s*\)$', str_in.strip()):
                    str_in = str_in
                else:
                    str_in = str_in + " | & tee /dev/null"

                # The below statement can be enabled if prompt is required after the shell output
                # str_in_prompt = '''echo "${USER}@${HOST}:$PWD # " '''

                str_b = (str_in+"\n").encode("utf-8")
                try:
                    self.proc.stdin.write(str_b)
                    self.proc.stdin.flush()
                except:
                    logger.info("Couldn't write into csh stdin")

            elif response.netconf_command:
                logger.info((str(response.netconf_command)))
                logger.info(type(str(response.netconf_command)))
                str_in = str(response.netconf_command)

                str_b = (str_in+"\n").encode("utf-8")
                try:
                    self.proc.stdin.write(str_b)
                    self.proc.stdin.flush()
                except:
                    logger.info("Couldn't write into netconf stdin")

        logger.info("*************Connection closed gracefully**************")


    def Intial_hand_shake(self, stub):
        client_name = self.client_name
        client_name_rpc = nc_grpc_pb2.NcgrpcInitializeRequest(
            instance_id = int(os.getpid()),
            device_id = client_name,
            secret_key = self.secret_key
        )
        logger.info("started initial hand shake")
        response, call = stub.NcgrpcInitialize.with_call(client_name_rpc,
                                         metadata=(
                                             ('send_data', 'send_data'),
                                         ))

        tmp_list = []
        for key, value in call.trailing_metadata():
            logger.info("Greeter client received trailing metadata: key={} value={}".format(key, value))
            temp_tuple = (key,value)
            self.meta_data.append(temp_tuple)

        logger.info("Ended the intial hand shake")
        if (response.session_type) == 0:
            return 1
        elif (response.session_type) == 1:
            return 2
        else:
            return 0

    def start_grpc_session(self):
        # global trusted_certs_input

        trusted_certs = self.trusted_certs_input
        trusted_certs = trusted_certs.replace("-----BEGIN CERTIFICATE-----", "-----BEGIN CERTIFICATE-----\n")
        trusted_certs = trusted_certs.replace("-----END CERTIFICATE-----", "\n-----END CERTIFICATE-----\n")
        trusted_certs = trusted_certs.rstrip("\n")
        trusted_certs = trusted_certs.encode()

        creds = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

        if mgmt_status_client == 1:
            jcs.set_routing_instance("mgmt_junos")

        with grpc.secure_channel(self.device+':'+self.port, creds) as self.channel:
            logger.info("A secure channel has been established")
            stub = nc_grpc_pb2.NcgrpcStub(self.channel)
            logger.info("NcgrpcStub loaded")
            try:
                response = stub.NcgrpcServerStatusGet(
                    nc_grpc_pb2.NcgrpcServerStatusGetRequest(
                        req = 0
                    )
                )
                logger.info("Response received for is server running function")
                if response.status == 1:
                    pass
            except:
                logger.info("******************** Server is down **********************")
                self.server_down = 1
                return

            status = self.Intial_hand_shake(stub)
            if status == 1 or status == 2:
                self.receive_cmds(stub, status)


    def start_app(self):
        global clients
        try:
            self.start_grpc_session()
        except:
            self.server_down = 1
            logger.info("***grpc session broke***")

        try:
            self.proc.stdin.close()
            self.proc.stdout.close()
        except:
            pass
        try:
            self.proc.terminate()
        except:
            pass
        clients.remove(self)
        return


# A new client connection will be always waiting the at server's end to connect
# whenever server wants
def manage_clients(device, secret_key, trusted_certs_input, port, client_name):
    global clients
    while 1:
        client = nc_grpc_app(device, secret_key, trusted_certs_input, port, client_name)
        logger.info("Manage clients function is called and entered in a while loop")
        t1 = threading.Thread(target=client.start_app,)
        t1.start()
        clients.append(client)
        logger.info("Manage_clients: A client has started in a separate thread")
        logger.info("Manage_clients: Going to wait, it will come out and start new connection \
                    request, when present connection is utilized")
        while 1:
            if client.server_down == 1:
                logger.info("Manage_clients: Server is down, Not force killing all the threads")
                # If somehow other threads are alive, let them be alive,
                # need not force kill the threads
                return
            if client.client_running != 1:
                time.sleep(1)
            elif client.client_running == 1:
                logger.info("Manage_clients: Previous session request is accepted, now sending another client request")
                break
        logger.info("Manage_clients: Came out of while loop")


# This is used to check if the server the client tries to connect is running or not
def is_server_running(device, port, trusted_certs):
    logger.info("is server running called")
    trusted_certs = trusted_certs.replace("-----BEGIN CERTIFICATE-----", "-----BEGIN CERTIFICATE-----\n")
    trusted_certs = trusted_certs.replace("-----END CERTIFICATE-----", "\n-----END CERTIFICATE-----\n")
    trusted_certs = trusted_certs.rstrip("\n")
    trusted_certs = trusted_certs.encode()

    creds = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
    try:
        if mgmt_status_client == 1:
            jcs.set_routing_instance("mgmt_junos")
        with grpc.secure_channel(device+':'+port, creds) as channel:
            stub = nc_grpc_pb2.NcgrpcStub(channel)
            logger.info("calling the server status stub")
            response = stub.NcgrpcServerStatusGet(
                nc_grpc_pb2.NcgrpcServerStatusGetRequest(
                    req = 0
                )
            )
            logger.info("Response received from is server running")
            if response.status == 1:
                return 1
            channel.close()
    except:
        return 0


# the function is called to restart or add a new client with new config,
# whenever there's a config change
# This function is always called in a new process using python multiprocessing
# library, so that each client runs as different process
def run_client(device_id, secret, servers, wait_time, reconnect_strategy, mgmt_status, queue):
    global clients
    global mgmt_status_client
    mgmt_status_client = mgmt_status
    check_from_start = 0
    while 1:

        logger.info("Entering into the for loop for list of servers")
        for server in servers:
            if 'port' not in server.keys():
                server['port'] = 443
            while True:
                if(is_server_running(server['name'], str(server['port']), server['trusted-cert']) == 1):
                    clients = []
                    manage_clients(server['name'], secret, server['trusted-cert'], str(server['port']), device_id)

                    outb_client = None
                    while not queue.empty():
                        outb_client = queue.get()

                    if (outb_client):
                        if 'waittime' in outb_client.keys():
                            wait_time = outb_client['waittime']
                        if 'reconnect-strategy' in outb_client.keys():
                            if outb_client['reconnect-strategy'] == "in-order":
                                reconnect_strategy = 1
                            elif outb_client['reconnect-strategy'] == "sticky":
                                reconnect_strategy = 2

                    if reconnect_strategy == 1:
                        check_from_start = 1
                        break
                    elif reconnect_strategy == 2:
                        logger.info("Checking again the same server as sticky is configured")
                        continue
                else:
                    check_from_start = 0
                    break
            if reconnect_strategy == 1 and check_from_start ==1:
                logger.info("Checking from the start again, in-order configured")
                check_from_start = 0
                break

        outb_client = None
        while not queue.empty():
            outb_client = queue.get()

        if (outb_client):
            if 'waittime' in outb_client.keys():
                wait_time = outb_client['waittime']
            if 'reconnect-strategy' in outb_client.keys():
                if outb_client['reconnect-strategy'] == "in-order":
                    reconnect_strategy = 1
                elif outb_client['reconnect-strategy'] == "sticky":
                    reconnect_strategy = 2

        logger.info("wait_time = {} *** reconnect_strategy = {} ".format(wait_time, reconnect_strategy))
        logger.info("{} sleeping for wait time".format(device_id))
        time.sleep(int(wait_time))
