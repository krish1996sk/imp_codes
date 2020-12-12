"""This is test gRPC server implemented to test the gRPC client"""

from __future__ import print_function
from concurrent import futures
import time
import math
import logging
import sys
import os,socket,json
import argparse
import signal

import grpc
import subprocess
import select
import threading

import jnx_netconf_service_pb2 as nc_grpc_pb2
import jnx_netconf_service_pb2_grpc as nc_grpc_pb2_grpc

# global space
client_list = {}
client_list_detail = {}
connections = {}
server = None

keys_location = os.path.dirname(os.path.realpath(sys.argv[0]))

#Create and configure logger
logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger('nc_grpc_server')

fileHandler = logging.FileHandler(keys_location + '/nc_grpc_server.log')
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)


def daemonize():
    """Deamonize class. UNIX double fork mechanism."""
    global keys_location
    logger.info(keys_location)

    try:
        pid = os.fork()
        if pid > 0:
            # exit first parent
            sys.exit(0)
    except OSError as err:
        sys.stderr.write('fork #1 failed: {0}\n'.format(err))
        sys.exit(1)


    logger.info("First parent process is exited")

    # decouple from parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)

    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent
            sys.exit(0)
    except OSError as err:
        sys.stderr.write('fork #2 failed: {0}\n'.format(err))
        sys.exit(1)

    logger.info("Second parent process is exited")

    # redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    logger.info("File descriptors redirection completed")


def close_socket(listen_s):
    try:
        listen_s.shutdown()
    except:
        pass
    try:
        listen_s.close()
    except:
        pass


class UserInputTimeoutError(Exception):
    pass

def print_data(request_iterator, c):
    try:
        logger.info("print_data: Inside print data thread")
        prev_message = []
        logger.info("print_data: Entered the simultaneous thread print data")
        for request_point in request_iterator:
            logger.info("print_data: Inside request iterator")
            logger.info(str(request_point.message).rstrip())
            try:
                c.send((str(request_point.message).rstrip()).encode())
            except:
                pass
            prev_message.append(str(request_point.message).rstrip())
            if (str(request_point.message).rstrip()).startswith('client is stopping,'):
                logger.info("*****print statement breaking******")
                return
    except:
        c.send(("client is stopping,").encode())
        logger.info("*********************client connection lost*********************")
        return


class Ncgrpc(nc_grpc_pb2_grpc.NcgrpcServicer):
    """Provides methods that implement functionality of NetconfRpc server."""

    def __init__(self):
        logger.info("***************************Constructor called, Ncgrpc class constructed*************************************")

    def __del__(self):
        logger.info("Destructor called, Ncgrpc deleted.")

    def NcgrpcServerStatusGet(self, request, context):
        logger.info("is server running rpc called")
        return nc_grpc_pb2.NcgrpcServerStatusGetResponse(
            status = 1
        )

    def NcgrpcCommandGet(self, request_iterator, context):
        global connections

        meta_dict = {}

        for key, value in context.invocation_metadata():
            logger.info('Received initial metadata: key={} value={}'.format(key, value))
            meta_dict.update({key:value})

        conn = connections[context.peer()]
        session_type_self = meta_dict["conn_type"]



        t1 = threading.Thread(target=print_data, args=(request_iterator,conn,))
        t1.start()

        while True:
            data_r = conn.recv(1024)
            logger.info(data_r)
            logger.info("Data received from request session ")
            if session_type_self == "netconf":
                if not (t1.isAlive()):
                    logger.info("NcgrpcCommandGet: Other thread is closed")
                    break
                if data_r.decode().strip() == "":
                    logger.info("NcgrpcCommandGet: Request session script closed")
                    yield nc_grpc_pb2.NcgrpcCommandGetResponse(
                        netconf_command = "<>",
                        kill_signal = 2)
                    t1.join()
                    break
                logger.info(data_r.decode())

                cmd_new = str(data_r.decode().strip())
                yield nc_grpc_pb2.NcgrpcCommandGetResponse(
                    netconf_command = cmd_new,
                    kill_signal = 0)
                # if cmd_new == "<>":
                #     t1.join()
                #     break

            elif session_type_self == "csh":
                if not (t1.isAlive()):
                    logger.info("NcgrpcCommandGet: Other thread is closed")
                    break

                if data_r.decode().strip() == "":
                    logger.info("NcgrpcCommandGet: Request session script closed")
                    yield nc_grpc_pb2.NcgrpcCommandGetResponse(
                        csh_command = "exit",
                        kill_signal = 2)
                    t1.join()
                    break

                logger.info(data_r.decode())

                cmd_new = str(data_r.decode().strip())
                yield nc_grpc_pb2.NcgrpcCommandGetResponse(
                    csh_command = cmd_new,
                    kill_signal = 0)
                # The below code is commented unlike in netconf case, as one 
                # should not close the session based on exit statement during csh mode
                # if cmd_new == "exit":
                #     t1.join()
                #     break

        connections.pop(context.peer())
        logger.info("****************** Good Bye*****RPC Ended ********************")

    def NcgrpcInitialize(self, request, context):
        global client_list
        global connections
        global client_list_detail
        global keys_location
        message_auth = request.device_id
        grpc_app_id = request.instance_id
        secret_key = request.secret_key
        logger.info(type(message_auth))
        logger.info(message_auth)
        client_name = message_auth

        for key, value in context.invocation_metadata():
            logger.info("NcgrpcInitialize: Received initial metadata(Initial handshake): key={} value={}".format(key, value))

        if client_name not in client_list_detail.keys() or (client_name in client_list_detail.keys() and grpc_app_id != client_list_detail[client_name][3]):
            logger.info("NcgrpcInitialize: Client is restarted or a new client is trying to connect")
            listen_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listen_s.bind(('localhost', 0))
            listen_s.listen()
            port = listen_s.getsockname()[1]
            port_str = str(port)
            data = {client_name: [port_str, listen_s, 1, grpc_app_id]}
            if client_name in client_list_detail.keys():
                close_socket(client_list_detail[client_name][1])
            client_list_detail.update(data)
            data = {client_name: port_str}
            client_list.update(data)
            with open(keys_location + '/server_data.json', 'w+') as outfile:
                json.dump(client_list, outfile)
        else:
            listen_s = client_list_detail[client_name][1]
            port = int(client_list_detail[client_name][0])
            port_str = str(port)
            client_list_detail[client_name][2] = client_list_detail[client_name][2] +1
            logger.info("NcgrpcInitialize: else statement executed properly")


        logger.info("Listenning")
        while True:
            c, addr = listen_s.accept()
            logger.info("Connection received")
            first_message = c.recv(1024)

            logger.info("Initial hand shake completed and the client is trusted")
            rep_mes = str(first_message.decode().strip())
            logger.info(rep_mes)
            index = rep_mes.find(':')
            secret_key_from_script = rep_mes[index+1:]
            rep_mes = rep_mes[0:index]
            if secret_key == secret_key_from_script:
                c.send(("correct secret key").encode())
                break
            else:
                c.send(("wrong secret key").encode())

        context.set_trailing_metadata((
            ('port', port_str),
            ('conn_type', rep_mes),
        ))
        logger.info(connections)
        connections.update({context.peer():c})
        logger.info(connections)
        logger.info("Going to return value from initial handshake")
        try:
            if rep_mes == "netconf":
                return nc_grpc_pb2.NcgrpcInitializeResponse(
                    session_type = 0
                )
            elif rep_mes == "csh":
                return nc_grpc_pb2.NcgrpcInitializeResponse(
                    session_type = 1
                )
        except:
            try:
                listen_s.shutdown()
            except:
                pass
            try:
                listen_s.close()
            except:
                pass


def serve():
    logger.info("Serve function is called")
    global port
    global server
    global keys_location
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    nc_grpc_pb2_grpc.add_NcgrpcServicer_to_server(
        Ncgrpc(), server)

    logger.info("Server object is created")

    with open(keys_location + '/server.key', 'rb') as f:
       private_key = f.read()
    with open(keys_location + '/server.crt', 'rb') as f:
       certificate_chain = f.read()

    logger.info("Read the certificates")
    server_credentials = grpc.ssl_server_credentials(((private_key, certificate_chain,),))
    server.add_secure_port('[::]:' + port, server_credentials)

    server.start()
    logger.info("Server started")
    server.wait_for_termination()


def signal_handler(sig, frame):
    global server
    global keys_location

    logger.info("Entered into signal_handler")
    if server != None:
        server.stop(1)
    logger.info("Stopping the grpc server gracefully")
    pid = os.getpid()
    try:
        os.remove(keys_location + "/server_data.json")
    except:
        pass
    os.kill(pid, signal.SIGKILL)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help='client port',
                        required=True)
    args = parser.parse_args()
    port = args.port
    daemonize()
    serve()
