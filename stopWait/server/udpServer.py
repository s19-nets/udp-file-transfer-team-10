import argparse
from enum import Enum
from os.path import isfile
from select import select
from socket import socket, AF_INET, SOCK_DGRAM
from struct import pack, unpack
from sys import argv, exit

# Create parser for user input
parser = argparse.ArgumentParser(description="Server that transfers a requested file to a client")
parser.add_argument('--port', required=False, default='50001',
                    help='server port')
parser.add_argument('--timeout', type=int, required=False, default=2,
                    help='number of seconds before re-sending a request to the server')
parser.add_argument('--maxtries', type=int, required=False, default=5,
                    help='number of tries of re-sending a request to the server before giving up')

# if len(argv) <= 1:
#     print('Error: file name was not specified')
#     exit(1)

# Parse given user input
args = parser.parse_args()
print(args)

# Enum class used to specify each state the client can be in
class State(Enum):
    READY = 0
    WAITING = 1
    EXITING = 2

# Enum class used to specify the type of a message
class MsgType(Enum):
    DATA = 0
    REQUEST = 1
    ACK = 2
    ERROR = 3

# Global variables used througout the system
server_socket = socket(AF_INET, SOCK_DGRAM)
server_addr =("",int(args.port))
server_socket.bind(server_addr)
last_ack_block = 0
max_tries = args.maxtries
state = State.READY
timeout = args.timeout
tries = 0
byte_s=0
f=0

# Method to encode a message before sending it [encoding based on the defined protocol]
def encode_msg(is_last_block, msgtype, ack_block, payload):
    is_last_block_id = 0x10 if is_last_block else 0
    metadata = is_last_block_id + msgtype.value

    struct_fmt = "{}s".format(len(payload))
    payload = payload.encode()

    msg = pack('B', metadata)  # numbers are packed into hexadecimal strings to send them and easily manage them
    msg += pack('I', ack_block)
    msg += pack(struct_fmt, payload)

    return msg


# Method to decode a received message [encoding based on the defined protocol]
def decode_msg(msg):
    metadata = unpack('B', msg[:1])[0]
    ack_block = unpack('I', msg[1:5])[0]
    payload = msg[5:].decode()

    msgtype_mask = 0x0F  # first byte of metadata is divided into [msgtype | ackblock]
    lastblock_mask = 0x10

    is_last_block = metadata & lastblock_mask == 1
    msgtype = metadata & msgtype_mask

    return is_last_block, msgtype, ack_block, payload


# Method to request a get operation to the server
def sendFile(sock, retry=True):
    global f, state, last_ack_block, client_addr, byte_s

    stop_writing = False

    if retry == True:
        msg = encode_msg(True, MsgType.DATA, last_ack_block, byte_s)
        sock.sendto(msg, client_addr)
    else:
        msg, client_addr = sock.recvfrom(100)
        _, msgtype, ack_block, payload = decode_msg(msg)
        print('Received '+payload+' '+str(msgtype))

        if msgtype == 1:
            try:
                f = open(str(payload), 'r')
            except FileNotFoundError:
                print('Error: specified file was not found')
                exit(1)
            byte_s = f.read(100)
            print(byte_s)
            state = State.WAITING
            stop_writing = is_last_block
            msg = encode_msg(True, MsgType.DATA, last_ack_block, byte_s)
            sock.sendto(msg, client_addr)
        elif msgtype == 2:
            if ack_block == last_ack_block:  # checks that the received block is the next in the sequence
                last_ack_block += 1
                byte_s = f.read(100)
                state = State.WAITING
                stop_writing = is_last_block
                msg = encode_msg(True, MsgType.DATA, last_ack_block, byte_s)
                sock.sendto(msg, client_addr)
        elif msgtype == MsgType.ERROR:
            print(payload)
            exit(1)

    return stop_writing


# map socket to function to call when socket is....
read_sockfunc = {}  # ready for reading
write_sockfunc = {}  # ready for writing
error_sockfunc = {}  # broken

read_sockfunc[server_socket] = sendFile

running = True
while running:
    read_rdyset, write_rdyset, err_rdyset = select(list(read_sockfunc.keys()),
                                                   list(write_sockfunc.keys()),
                                                   list(error_sockfunc.keys()),
                                                   timeout)
    if not read_rdyset and not write_rdyset and not err_rdyset:
        if state == 1:
            print("retry")
            keep_trying = True
            if tries == max_tries:
                print("Error: maximum number of tries was reached, would you like to keep trying? [t | f]")
                running = input('prompt') == "t"
            elif running:
                tries += 1
                sendFile(server_socket)
    else:
        print("a msg was received")
        tries = 0
        for sock in read_rdyset:
            if read_sockfunc[sock](sock, False):
                running = False
                break
